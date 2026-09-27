from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import CUSTOM_SUITES_PATH


CUSTOM_SUITE_SCHEMA_VERSION = 2


def configured_test_identity(type_ref: str, params: dict[str, object]) -> str:
    if not isinstance(type_ref, str) or not type_ref.strip():
        raise ValueError('configured test type_ref must not be empty')
    if not isinstance(params, dict):
        raise ValueError('configured test params must be an object')
    try:
        return json.dumps(
            {'type_ref': type_ref.strip(), 'params': params},
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError('configured test params must be JSON-serializable') from exc


@dataclass(frozen=True, slots=True)
class CustomSuiteTest:
    type_ref: str
    instance_id: str
    params: dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.type_ref, str) or not self.type_ref.strip():
            raise ValueError('custom suite test type_ref must not be empty')
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError('custom suite test instance_id must not be empty')
        configured_test_identity(self.type_ref, self.params)


@dataclass(frozen=True, slots=True)
class CustomSuite:
    name: str
    repeats: int
    tests: tuple[CustomSuiteTest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('custom suite name must not be empty')
        if isinstance(self.repeats, bool) or not isinstance(self.repeats, int) or not 1 <= self.repeats <= 100:
            raise ValueError('custom suite repeats must be an integer between 1 and 100')
        if not isinstance(self.tests, tuple) or not self.tests:
            raise ValueError('custom suite must contain at least one configured test')
        identities = [
            configured_test_identity(test.type_ref, test.params)
            for test in self.tests
        ]
        if len(identities) != len(set(identities)):
            raise ValueError('custom suite contains duplicate configured tests')


def _scope_value(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError('custom suite scope must not be empty')
    return scope.strip()


def _suite_from_payload(payload: object) -> CustomSuite:
    if not isinstance(payload, dict):
        raise ValueError('custom suite must be an object')
    name = payload.get('name')
    repeats = payload.get('repeats')
    raw_tests = payload.get('tests')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('custom suite name must be a non-empty string')
    if isinstance(repeats, bool) or not isinstance(repeats, int):
        raise ValueError('custom suite repeats must be an integer')
    if not isinstance(raw_tests, list):
        raise ValueError('custom suite tests must be an array')

    tests: list[CustomSuiteTest] = []
    for item in raw_tests:
        if not isinstance(item, dict):
            raise ValueError('custom suite test must be an object')
        type_ref = item.get('type_ref')
        instance_id = item.get('instance_id')
        params = item.get('params')
        if not isinstance(type_ref, str) or not type_ref.strip():
            raise ValueError('custom suite test type_ref must be a non-empty string')
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError('custom suite test instance_id must be a non-empty string')
        if not isinstance(params, dict):
            raise ValueError('custom suite test params must be an object')
        tests.append(CustomSuiteTest(
            type_ref=type_ref.strip(),
            instance_id=instance_id.strip(),
            params=dict(params),
        ))

    return CustomSuite(
        name=name.strip(),
        repeats=repeats,
        tests=tuple(tests),
    )


def _suite_payload(suite: CustomSuite) -> dict[str, object]:
    return {
        'name': suite.name,
        'repeats': suite.repeats,
        'tests': [{
            'type_ref': test.type_ref,
            'instance_id': test.instance_id,
            'params': test.params,
        } for test in suite.tests],
    }


def _validate_suite_names(suites: tuple[CustomSuite, ...]) -> None:
    names = [suite.name.casefold() for suite in suites]
    if len(names) != len(set(names)):
        raise ValueError('custom suite names must be unique within a scope')


def _load_scopes(path: Path) -> dict[str, tuple[CustomSuite, ...]]:
    target = path.expanduser()
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid custom suite store: {target}: {exc}') from exc
    if not isinstance(payload, dict) or payload.get('schema_version') != CUSTOM_SUITE_SCHEMA_VERSION:
        raise ValueError('unsupported custom suite store schema')
    raw_scopes = payload.get('scopes')
    if not isinstance(raw_scopes, dict):
        raise ValueError('custom suite scopes must be an object')

    scopes: dict[str, tuple[CustomSuite, ...]] = {}
    for raw_scope, raw_suites in raw_scopes.items():
        scope = _scope_value(raw_scope)
        if scope != raw_scope:
            raise ValueError('custom suite scope keys must be canonical')
        if not isinstance(raw_suites, list):
            raise ValueError(f'custom suite scope {scope!r} must be an array')
        suites = tuple(_suite_from_payload(item) for item in raw_suites)
        _validate_suite_names(suites)
        scopes[scope] = tuple(sorted(suites, key=lambda suite: suite.name.casefold()))
    return scopes


def load_custom_suites(
    scope: str,
    path: Path = CUSTOM_SUITES_PATH,
) -> tuple[CustomSuite, ...]:
    value = _scope_value(scope)
    return _load_scopes(path).get(value, ())


def save_custom_suites(
    scope: str,
    suites: tuple[CustomSuite, ...] | list[CustomSuite],
    path: Path = CUSTOM_SUITES_PATH,
) -> Path:
    value = _scope_value(scope)
    normalized = tuple(suites)
    if not all(isinstance(suite, CustomSuite) for suite in normalized):
        raise ValueError('custom suite store accepts CustomSuite values only')
    _validate_suite_names(normalized)

    scopes = _load_scopes(path)
    scopes[value] = tuple(sorted(normalized, key=lambda suite: suite.name.casefold()))
    payload = {
        'schema_version': CUSTOM_SUITE_SCHEMA_VERSION,
        'scopes': {
            scope_name: [_suite_payload(suite) for suite in scoped_suites]
            for scope_name, scoped_suites in sorted(scopes.items())
        },
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
