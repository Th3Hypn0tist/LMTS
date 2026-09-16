from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_TEST_REF_RE = re.compile(
    r'^(?P<type_id>[A-Za-z0-9_.-]+)@(?P<version>[^#\s]+)(?:#(?P<instance_id>[^#\s]+))?$'
)


@dataclass(frozen=True, slots=True)
class TestIdentity:
    type_id: str
    version: str
    instance_id: str | None = None

    def __post_init__(self) -> None:
        type_id = str(self.type_id).strip()
        version = str(self.version).strip()
        instance_id = None if self.instance_id is None else str(self.instance_id).strip()
        if not type_id or not version:
            raise ValueError('test identity requires non-empty type_id and version')
        if any(char.isspace() for char in type_id + version):
            raise ValueError('test identity tokens must not contain whitespace')
        if '@' in type_id or '#' in type_id or '#' in version:
            raise ValueError('invalid test identity token')
        if instance_id is not None:
            if not instance_id or any(char.isspace() for char in instance_id) or '#' in instance_id:
                raise ValueError('test instance_id must be a non-empty token without #')
        object.__setattr__(self, 'type_id', type_id)
        object.__setattr__(self, 'version', version)
        object.__setattr__(self, 'instance_id', instance_id)

    @property
    def type_ref(self) -> str:
        return f'{self.type_id}@{self.version}'

    @property
    def ref(self) -> str:
        if self.instance_id is None:
            return self.type_ref
        return f'{self.type_ref}#{self.instance_id}'

    def to_dict(self) -> dict[str, str | None]:
        return {
            'type_id': self.type_id,
            'version': self.version,
            'type_ref': self.type_ref,
            'instance_id': self.instance_id,
            'ref': self.ref,
        }


def parse_test_ref(value: str) -> TestIdentity:
    ref = str(value).strip()
    match = _TEST_REF_RE.fullmatch(ref)
    if match is None:
        raise ValueError(f'invalid canonical test_ref: {value!r}')
    return TestIdentity(
        type_id=match.group('type_id'),
        version=match.group('version'),
        instance_id=match.group('instance_id'),
    )


def identity_for_test(test: Any) -> TestIdentity:
    configured_ref = getattr(test, 'ref', None)
    if isinstance(configured_ref, str) and configured_ref.strip():
        return parse_test_ref(configured_ref)
    type_id = str(getattr(test, 'id', '') or '').strip()
    version = str(getattr(test, 'version', '') or '').strip()
    return TestIdentity(type_id=type_id, version=version)


def test_ref(test: Any) -> str:
    return identity_for_test(test).ref


def test_snapshot(test: Any) -> dict[str, Any]:
    identity = identity_for_test(test)
    snapshot: dict[str, Any] = {'identity': identity.to_dict()}
    params = getattr(test, 'params', None)
    if isinstance(params, dict):
        snapshot['configuration'] = dict(params)
    minimum_level = getattr(test, 'minimum_level', None)
    if minimum_level is not None:
        snapshot['minimum_level'] = str(minimum_level)
    mandatory = getattr(test, 'mandatory', None)
    if mandatory is not None:
        snapshot['mandatory'] = bool(mandatory)
    requirements = getattr(test, 'requirements', None)
    subject_kinds = getattr(requirements, 'subject_kinds', None)
    if isinstance(subject_kinds, tuple):
        snapshot['subject_kinds'] = list(subject_kinds)
    category = getattr(test, 'category', None)
    subcategory = getattr(test, 'subcategory', None)
    if category is not None or subcategory is not None:
        if not isinstance(category, str) or not category.strip():
            raise ValueError('configured test category must be a non-empty string')
        if not isinstance(subcategory, str) or not subcategory.strip():
            raise ValueError('configured test subcategory must be a non-empty string')
        snapshot['taxonomy'] = {
            'category': category,
            'subcategory': subcategory,
            'ref': f'{category}/{subcategory}',
        }
    return snapshot
