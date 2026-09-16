from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib import request

from .executor import RuntimeExecutor
from .models import ModelCapabilities, NormalizedPerformance, NormalizedResponse, NormalizedTiming, NormalizedUsage
from .paths import RUNTIME_SECRETS_PATH, RUNTIME_TARGETS_PATH
from .subject import EvaluationSubject, SubjectMember

RUNTIME_TARGETS_SCHEMA_VERSION = 1
RUNTIME_SECRETS_SCHEMA_VERSION = 1
DEFAULT_RUNTIME_TARGETS_PATH = RUNTIME_TARGETS_PATH
DEFAULT_RUNTIME_SECRETS_PATH = RUNTIME_SECRETS_PATH
RuntimeTransport = Literal['http', 'subprocess']
RuntimeKind = Literal['bot', 'composition']


@dataclass(frozen=True, slots=True)
class RuntimeTargetDefinition:
    id: str
    kind: RuntimeKind
    transport: RuntimeTransport
    label: str = ''
    endpoint: str = ''
    command: tuple[str, ...] = ()
    timeout_seconds: float = 900.0
    members: tuple[SubjectMember, ...] = ()
    auth_header: str = ''
    auth_prefix: str = ''
    configuration: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError('runtime target id must not be empty')
        if self.kind not in {'bot', 'composition'}:
            raise ValueError(f'unsupported runtime target kind: {self.kind}')
        if self.transport == 'http':
            if not self.endpoint.startswith(('http://', 'https://')):
                raise ValueError('HTTP runtime target requires an http:// or https:// endpoint')
        elif self.transport == 'subprocess':
            if not self.command:
                raise ValueError('subprocess runtime target requires a command')
            if self.auth_header or self.auth_prefix:
                raise ValueError('subprocess runtime target cannot define HTTP authentication')
        else:
            raise ValueError(f'unsupported runtime target transport: {self.transport}')
        if self.auth_header and any(char in self.auth_header for char in '\r\n:'):
            raise ValueError('runtime target auth header must be a canonical header name without colon')
        if '\r' in self.auth_prefix or '\n' in self.auth_prefix:
            raise ValueError('runtime target auth prefix must not contain line breaks')
        if self.kind == 'composition' and not self.members:
            raise ValueError('composition runtime target requires members')
        if self.timeout_seconds <= 0:
            raise ValueError('runtime target timeout must be positive')

    @property
    def subject(self) -> EvaluationSubject:
        if self.kind == 'bot':
            return EvaluationSubject.for_bot(
                self.id,
                label=self.label,
                configuration=self.configuration,
                metadata=self.metadata,
            )
        return EvaluationSubject.for_composition(
            self.id,
            self.members,
            label=self.label,
            configuration=self.configuration,
            metadata=self.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': self.kind,
            'transport': self.transport,
            'label': self.label,
            'endpoint': self.endpoint,
            'command': list(self.command),
            'timeout_seconds': self.timeout_seconds,
            'members': [{'ref': item.ref, 'role': item.role} for item in self.members],
            'auth_header': self.auth_header,
            'auth_prefix': self.auth_prefix,
            'configuration': dict(self.configuration),
            'metadata': dict(self.metadata),
            'capabilities': {
                'text': self.capabilities.text,
                'vision': self.capabilities.vision,
                'tools': self.capabilities.tools,
                'structured_output': self.capabilities.structured_output,
                'workspace_read': self.capabilities.workspace_read,
                'workspace_write': self.capabilities.workspace_write,
                'multi_file_output': self.capabilities.multi_file_output,
            },
        }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_suffix(path.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(text, encoding='utf-8')
    try:
        temp.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def load_runtime_secrets(path: Path = DEFAULT_RUNTIME_SECRETS_PATH) -> dict[str, str]:
    path = path.expanduser()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != RUNTIME_SECRETS_SCHEMA_VERSION:
        raise ValueError('unsupported runtime secrets schema')
    raw = payload.get('keys')
    if not isinstance(raw, dict):
        raise ValueError('runtime secrets keys must be an object')
    output: dict[str, str] = {}
    for target_id, value in raw.items():
        if not isinstance(target_id, str) or not target_id.strip():
            raise ValueError('runtime secret target id must be a non-empty string')
        if not isinstance(value, str) or not value:
            raise ValueError(f'runtime secret for {target_id} must be a non-empty string')
        output[target_id] = value
    return output


def save_runtime_secrets(keys: dict[str, str], path: Path = DEFAULT_RUNTIME_SECRETS_PATH) -> Path:
    clean: dict[str, str] = {}
    for target_id, value in keys.items():
        target = str(target_id).strip()
        if not target:
            raise ValueError('runtime secret target id must be non-empty')
        if not isinstance(value, str) or not value:
            raise ValueError(f'runtime secret for {target} must be non-empty')
        clean[target] = value
    return _atomic_json_write(path, {'schema_version': RUNTIME_SECRETS_SCHEMA_VERSION, 'keys': clean})


def set_runtime_key(target_id: str, key: str, path: Path = DEFAULT_RUNTIME_SECRETS_PATH) -> Path:
    target = target_id.strip()
    if not target:
        raise ValueError('runtime target id must be non-empty')
    if not key:
        raise ValueError('runtime target key must be non-empty')
    keys = load_runtime_secrets(path)
    keys[target] = key
    return save_runtime_secrets(keys, path)


def delete_runtime_key(target_id: str, path: Path = DEFAULT_RUNTIME_SECRETS_PATH) -> None:
    keys = load_runtime_secrets(path)
    if target_id not in keys:
        return
    del keys[target_id]
    if keys:
        save_runtime_secrets(keys, path)
    else:
        path = path.expanduser()
        if path.exists():
            path.unlink()


def _normalized_response(payload: dict[str, Any], elapsed_ms: float) -> NormalizedResponse:
    text = payload.get('text')
    if not isinstance(text, str):
        raise ValueError('LMTS Runtime Protocol response requires string field: text')
    usage = payload.get('usage') if isinstance(payload.get('usage'), dict) else {}
    timing = payload.get('timing') if isinstance(payload.get('timing'), dict) else {}
    performance = payload.get('performance') if isinstance(payload.get('performance'), dict) else {}
    return NormalizedResponse(
        text=text,
        finish_reason=str(payload.get('finish_reason')) if payload.get('finish_reason') is not None else None,
        usage=NormalizedUsage(
            input_tokens=usage.get('input_tokens') if isinstance(usage.get('input_tokens'), int) else None,
            output_tokens=usage.get('output_tokens') if isinstance(usage.get('output_tokens'), int) else None,
        ),
        timing=NormalizedTiming(
            ttft_ms=float(timing['ttft_ms']) if isinstance(timing.get('ttft_ms'), (int, float)) else None,
            total_ms=float(timing['total_ms']) if isinstance(timing.get('total_ms'), (int, float)) else elapsed_ms,
            load_ms=float(timing['load_ms']) if isinstance(timing.get('load_ms'), (int, float)) else None,
            prompt_eval_ms=float(timing['prompt_eval_ms']) if isinstance(timing.get('prompt_eval_ms'), (int, float)) else None,
            generation_ms=float(timing['generation_ms']) if isinstance(timing.get('generation_ms'), (int, float)) else None,
        ),
        performance=NormalizedPerformance(
            prompt_tokens_per_second=float(performance['prompt_tokens_per_second']) if isinstance(performance.get('prompt_tokens_per_second'), (int, float)) else None,
            generation_tokens_per_second=float(performance['generation_tokens_per_second']) if isinstance(performance.get('generation_tokens_per_second'), (int, float)) else None,
        ),
        raw=dict(payload),
    )


def _http_generate(definition: RuntimeTargetDefinition, prompt: str) -> NormalizedResponse:
    body = json.dumps({'protocol': 'lmts.runtime.v1', 'prompt': prompt}, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json'}
    if definition.auth_header:
        keys = load_runtime_secrets()
        key = keys.get(definition.id)
        if key is None:
            raise ValueError(f'HTTP runtime target requires configured key: {definition.id}')
        headers[definition.auth_header] = f'{definition.auth_prefix}{key}'
    req = request.Request(
        definition.endpoint,
        data=body,
        method='POST',
        headers=headers,
    )
    started = time.perf_counter()
    with request.urlopen(req, timeout=definition.timeout_seconds) as response:
        payload = json.loads(response.read().decode('utf-8'))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if not isinstance(payload, dict):
        raise ValueError('LMTS Runtime Protocol response must be a JSON object')
    return _normalized_response(payload, elapsed_ms)


def _subprocess_generate(definition: RuntimeTargetDefinition, prompt: str) -> NormalizedResponse:
    body = json.dumps({'protocol': 'lmts.runtime.v1', 'prompt': prompt}, ensure_ascii=False) + '\n'
    started = time.perf_counter()
    completed = subprocess.run(
        list(definition.command),
        input=body,
        capture_output=True,
        text=True,
        timeout=definition.timeout_seconds,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if completed.returncode != 0:
        raise RuntimeError(f'runtime target exited with code {completed.returncode}: {completed.stderr.strip()}')
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f'LMTS Runtime Protocol subprocess returned invalid JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('LMTS Runtime Protocol response must be a JSON object')
    return _normalized_response(payload, elapsed_ms)


def executor_from_definition(definition: RuntimeTargetDefinition) -> RuntimeExecutor:
    def generate_handler(prompt: str, sink) -> NormalizedResponse:
        response = _http_generate(definition, prompt) if definition.transport == 'http' else _subprocess_generate(definition, prompt)
        if sink is not None:
            from .models import ResponseStreamChunk
            sink(ResponseStreamChunk(source_id=definition.id, channel='text', text=response.text))
            sink(ResponseStreamChunk(source_id=definition.id, channel='meta', data={
                'finish_reason': response.finish_reason,
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'ttft_ms': response.timing.ttft_ms,
                'total_ms': response.timing.total_ms,
                'generation_tokens_per_second': response.performance.generation_tokens_per_second,
            }))
        return response

    return RuntimeExecutor(
        executor_id=definition.id,
        executor_kind=definition.kind,
        evaluation_subject=definition.subject,
        generate_handler=generate_handler,
        executor_capabilities=definition.capabilities,
        executor_metadata={
            'transport': definition.transport,
            'endpoint': definition.endpoint or None,
            'command': list(definition.command),
            'auth_header': definition.auth_header or None,
            'auth_configured': bool(definition.auth_header),
            **definition.metadata,
        },
    )


def _capabilities(raw: object) -> ModelCapabilities:
    data = raw if isinstance(raw, dict) else {}
    return ModelCapabilities(
        text=bool(data.get('text', True)),
        vision=data.get('vision') if isinstance(data.get('vision'), bool) else None,
        tools=data.get('tools') if isinstance(data.get('tools'), bool) else None,
        structured_output=data.get('structured_output') if isinstance(data.get('structured_output'), bool) else None,
        workspace_read=data.get('workspace_read') if isinstance(data.get('workspace_read'), bool) else None,
        workspace_write=data.get('workspace_write') if isinstance(data.get('workspace_write'), bool) else None,
        multi_file_output=data.get('multi_file_output') if isinstance(data.get('multi_file_output'), bool) else None,
    )


def _definition(raw: dict[str, Any]) -> RuntimeTargetDefinition:
    members_raw = raw.get('members') if isinstance(raw.get('members'), list) else []
    members = tuple(
        SubjectMember(str(item.get('ref') or ''), role=str(item.get('role')) if item.get('role') is not None else None)
        for item in members_raw
        if isinstance(item, dict)
    )
    command_raw = raw.get('command')
    if isinstance(command_raw, str):
        command = tuple(shlex.split(command_raw))
    elif isinstance(command_raw, list):
        command = tuple(str(item) for item in command_raw)
    else:
        command = ()
    return RuntimeTargetDefinition(
        id=str(raw.get('id') or '').strip(),
        kind=str(raw.get('kind') or '').strip(),
        transport=str(raw.get('transport') or '').strip(),
        label=str(raw.get('label') or '').strip(),
        endpoint=str(raw.get('endpoint') or '').strip(),
        command=command,
        timeout_seconds=float(raw.get('timeout_seconds') or 900.0),
        members=members,
        auth_header=str(raw.get('auth_header') or '').strip(),
        auth_prefix=str(raw.get('auth_prefix') or ''),
        configuration=dict(raw.get('configuration') or {}) if isinstance(raw.get('configuration'), dict) else {},
        metadata=dict(raw.get('metadata') or {}) if isinstance(raw.get('metadata'), dict) else {},
        capabilities=_capabilities(raw.get('capabilities')),
    )


def load_runtime_targets(path: Path = DEFAULT_RUNTIME_TARGETS_PATH) -> tuple[RuntimeTargetDefinition, ...]:
    path = path.expanduser()
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != RUNTIME_TARGETS_SCHEMA_VERSION:
        raise ValueError('unsupported runtime target schema')
    items = payload.get('targets')
    if not isinstance(items, list):
        raise ValueError('runtime target store targets must be a list')
    definitions = tuple(_definition(item) for item in items if isinstance(item, dict))
    ids = [item.id for item in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError('runtime target ids must be unique')
    return definitions


def save_runtime_targets(definitions: tuple[RuntimeTargetDefinition, ...], path: Path = DEFAULT_RUNTIME_TARGETS_PATH) -> Path:
    ids = [item.id for item in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError('runtime target ids must be unique')
    payload = {'schema_version': RUNTIME_TARGETS_SCHEMA_VERSION, 'targets': [item.to_dict() for item in definitions]}
    return _atomic_json_write(path, payload)
