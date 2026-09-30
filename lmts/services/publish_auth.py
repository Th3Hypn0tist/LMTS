from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from lmts.core.paths import PUBLISH_AUTH_PATH


PUBLISH_AUTH_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 15


class PublishAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MachinePublishCredential:
    endpoint: str
    system_id: str
    key_id: str
    secret: str

    @property
    def authorization_value(self) -> str:
        return f'{self.key_id}.{self.secret}'


class MachinePublishCredentialStore:
    def __init__(self, path: Path = PUBLISH_AUTH_PATH) -> None:
        self.path = path

    def save(self, credential: MachinePublishCredential) -> None:
        payload = {
            'schema_version': PUBLISH_AUTH_SCHEMA_VERSION,
            'endpoint': credential.endpoint,
            'system_id': credential.system_id,
            'publish_key_id': credential.key_id,
            'publish_secret': credential.secret,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + '.tmp')
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding='utf-8',
        )
        os.chmod(temp, 0o600)
        temp.replace(self.path)
        os.chmod(self.path, 0o600)

    def load(self, *, endpoint: str, system_id: str) -> MachinePublishCredential | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublishAuthenticationError('local publish credential is invalid') from exc
        if not isinstance(payload, dict) or payload.get('schema_version') != PUBLISH_AUTH_SCHEMA_VERSION:
            raise PublishAuthenticationError('local publish credential schema is invalid')
        if str(payload.get('endpoint') or '') != endpoint:
            return None
        if str(payload.get('system_id') or '') != system_id:
            return None
        key_id = str(payload.get('publish_key_id') or '').strip()
        secret = str(payload.get('publish_secret') or '').strip()
        if not key_id or not secret:
            raise PublishAuthenticationError('local publish credential is incomplete')
        return MachinePublishCredential(endpoint, system_id, key_id, secret)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _provision_url(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    path = parts.path
    base = path.rsplit('/', 1)[0] if '/' in path else ''
    return urlunsplit((parts.scheme, parts.netloc, f'{base}/provision.php', '', ''))


def _report_machine_identity(report: dict[str, object]) -> tuple[str, str, dict[str, object]]:
    records = report.get('records')
    if not isinstance(records, list) or not records:
        raise PublishAuthenticationError('report contains no records')

    user_id: str | None = None
    system_id: str | None = None
    system_context: dict[str, object] | None = None

    for item in records:
        if not isinstance(item, dict):
            continue
        provenance = item.get('provenance')
        evidence = item.get('evidence')
        if not isinstance(provenance, dict):
            raise PublishAuthenticationError('report record has no provenance')
        record_user = str(provenance.get('tester_user_id') or '').strip()
        record_system = str(provenance.get('system_id') or '').strip()
        if not record_user or not record_system:
            raise PublishAuthenticationError('report record is missing tester_user_id or system_id')
        if user_id is None:
            user_id, system_id = record_user, record_system
        elif user_id != record_user or system_id != record_system:
            raise PublishAuthenticationError('report mixes multiple user or system identities')

        if isinstance(evidence, dict):
            context = evidence.get('system_context')
            if isinstance(context, dict):
                if system_context is None:
                    system_context = context
                elif system_context != context:
                    raise PublishAuthenticationError('report contains conflicting system_context evidence')

    if user_id is None or system_id is None or system_context is None:
        raise PublishAuthenticationError('report has no usable machine identity evidence')
    return user_id, system_id, system_context


def provision_machine_credential(
    report: dict[str, object],
    endpoint: str,
    *,
    bearer_token: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MachinePublishCredential:
    _user_id, system_id, system_context = _report_machine_identity(report)
    body = json.dumps(
        {'system_id': system_id, 'system_context': system_context},
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    request = Request(
        _provision_url(endpoint),
        data=body,
        method='POST',
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f'Bearer {bearer_token}',
            'X-LMTS-Authorization': f'Bearer {bearer_token}',
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
            status = int(getattr(response, 'status', response.getcode()))
    except HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        detail = payload.get('error') if isinstance(payload, dict) else None
        raise PublishAuthenticationError(
            f'LMTS publish credential provisioning HTTP {exc.code}: '
            f'{detail or raw.strip() or exc.reason}'
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PublishAuthenticationError(f'LMTS publish credential provisioning failed: {exc}') from exc

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise PublishAuthenticationError(
            f'LMTS publish credential provisioning returned invalid JSON (HTTP {status})'
        ) from exc
    if status not in {200, 201} or not isinstance(payload, dict) or payload.get('ok') is not True:
        raise PublishAuthenticationError(f'LMTS publish credential provisioning failed: {payload!r}')

    returned_system = str(payload.get('system_id') or '').strip()
    key_id = str(payload.get('key_id') or '').strip()
    secret = str(payload.get('secret') or '').strip()
    if returned_system != system_id or not key_id or not secret:
        raise PublishAuthenticationError('LMTS publish credential provisioning response is incomplete')
    return MachinePublishCredential(endpoint, system_id, key_id, secret)


def ensure_machine_credential(
    report: dict[str, object],
    endpoint: str,
    *,
    bearer_token: str,
    store: MachinePublishCredentialStore | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MachinePublishCredential:
    _user_id, system_id, _context = _report_machine_identity(report)
    storage = store or MachinePublishCredentialStore()
    current = storage.load(endpoint=endpoint, system_id=system_id)
    if current is not None:
        return current
    credential = provision_machine_credential(
        report,
        endpoint,
        bearer_token=bearer_token,
        timeout=timeout,
    )
    storage.save(credential)
    return credential
