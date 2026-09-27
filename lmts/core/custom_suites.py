from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import CUSTOM_SUITES_PATH


CUSTOM_SUITE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CustomSuiteTest:
    type_ref: str
    instance_id: str
    params: dict[str, object]

    def __post_init__(self) -> None:
        if not self.type_ref.strip():
            raise ValueError('custom suite test type_ref must not be empty')
        if not self.instance_id.strip():
            raise ValueError('custom suite test instance_id must not be empty')


@dataclass(frozen=True, slots=True)
class CustomSuite:
    name: str
    repeats: int
    tests: tuple[CustomSuiteTest, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('custom suite name must not be empty')
        if isinstance(self.repeats, bool) or not isinstance(self.repeats, int) or not 1 <= self.repeats <= 100:
            raise ValueError('custom suite repeats must be an integer between 1 and 100')
        if not self.tests:
            raise ValueError('custom suite must contain at least one configured test')
        identities = [
            json.dumps(
                {'type_ref': test.type_ref, 'params': test.params},
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            )
            for test in self.tests
        ]
        if len(identities) != len(set(identities)):
            raise ValueError('custom suite contains duplicate configured tests')


def _suite_from_payload(payload: object) -> CustomSuite:
    if not isinstance(payload, dict):
        raise ValueError('custom suite must be an object')
    raw_tests = payload.get('tests')
    if not isinstance(raw_tests, list):
        raise ValueError('custom suite tests must be an array')
    tests: list[CustomSuiteTest] = []
    for item in raw_tests:
        if not isinstance(item, dict):
            raise ValueError('custom suite test must be an object')
        params = item.get('params')
        if not isinstance(params, dict):
            raise ValueError('custom suite test params must be an object')
        tests.append(CustomSuiteTest(
            type_ref=str(item.get('type_ref') or '').strip(),
            instance_id=str(item.get('instance_id') or '').strip(),
            params=dict(params),
        ))
    return CustomSuite(
        name=str(payload.get('name') or '').strip(),
        repeats=int(payload.get('repeats', 1)),
        tests=tuple(tests),
    )


def load_custom_suites(path: Path = CUSTOM_SUITES_PATH) -> tuple[CustomSuite, ...]:
    target = path.expanduser()
    if not target.is_file():
        return ()
    try:
        payload = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid custom suite store: {target}: {exc}') from exc
    if not isinstance(payload, dict) or payload.get('schema_version') != CUSTOM_SUITE_SCHEMA_VERSION:
        raise ValueError('unsupported custom suite store schema')
    raw_suites = payload.get('suites')
    if not isinstance(raw_suites, list):
        raise ValueError('custom suite store suites must be an array')
    suites = tuple(_suite_from_payload(item) for item in raw_suites)
    names = [suite.name.casefold() for suite in suites]
    if len(names) != len(set(names)):
        raise ValueError('custom suite names must be unique')
    return tuple(sorted(suites, key=lambda suite: suite.name.casefold()))


def save_custom_suites(
    suites: tuple[CustomSuite, ...] | list[CustomSuite],
    path: Path = CUSTOM_SUITES_PATH,
) -> Path:
    normalized = tuple(suites)
    names = [suite.name.casefold() for suite in normalized]
    if len(names) != len(set(names)):
        raise ValueError('custom suite names must be unique')
    payload = {
        'schema_version': CUSTOM_SUITE_SCHEMA_VERSION,
        'suites': [{
            'name': suite.name,
            'repeats': suite.repeats,
            'tests': [{
                'type_ref': test.type_ref,
                'instance_id': test.instance_id,
                'params': test.params,
            } for test in suite.tests],
        } for suite in sorted(normalized, key=lambda suite: suite.name.casefold())],
    }
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + f'.tmp-{os.getpid()}')
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.chmod(temp, 0o600)
    try:
        temp.replace(target)
        os.chmod(target, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return target
