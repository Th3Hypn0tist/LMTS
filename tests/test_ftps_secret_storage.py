from __future__ import annotations

import json

import pytest

from lmts.tools.ftp_profiles import FTPProfile, FTPProfiles, load_ftp_profiles, save_ftp_profiles


def profile() -> FTPProfile:
    return FTPProfile(
        name='publish',
        host='ftp.example.test',
        username='lmts',
        password_env='LMTS_FTPS_PUBLISH_PASSWORD',
        root='/reports',
        port=21,
    )


def test_ftps_profile_store_never_persists_password_value(tmp_path) -> None:
    path = save_ftp_profiles(FTPProfiles(profiles=(profile(),)), tmp_path / 'ftp_profiles.json')
    raw = path.read_text(encoding='utf-8')
    payload = json.loads(raw)
    stored = payload['profiles'][0]
    assert payload['schema_version'] == 3
    assert stored['password_env'] == 'LMTS_FTPS_PUBLISH_PASSWORD'
    assert 'password' not in stored
    assert 'secret-value' not in raw


def test_ftps_password_is_resolved_only_from_explicit_environment_reference() -> None:
    item = profile()
    assert item.resolve_password({'LMTS_FTPS_PUBLISH_PASSWORD': 'secret-value'}) == 'secret-value'
    with pytest.raises(RuntimeError, match='not set or empty'):
        item.resolve_password({})


def test_legacy_plaintext_ftps_store_fails_closed(tmp_path) -> None:
    path = tmp_path / 'ftp_profiles.json'
    path.write_text(
        json.dumps(
            {
                'schema_version': 2,
                'profiles': [
                    {
                        'name': 'legacy',
                        'host': 'ftp.example.test',
                        'username': 'lmts',
                        'password': 'plaintext-secret',
                        'root': '/reports',
                        'port': 21,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='contains plaintext passwords'):
        load_ftp_profiles(path)


def test_schema_three_rejects_injected_plaintext_password_field(tmp_path) -> None:
    path = tmp_path / 'ftp_profiles.json'
    path.write_text(
        json.dumps(
            {
                'schema_version': 3,
                'profiles': [
                    {
                        'name': 'bad',
                        'host': 'ftp.example.test',
                        'username': 'lmts',
                        'password_env': 'LMTS_FTPS_PASSWORD',
                        'password': 'must-not-exist',
                        'root': '/reports',
                        'port': 21,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='must not contain plaintext password fields'):
        load_ftp_profiles(path)
