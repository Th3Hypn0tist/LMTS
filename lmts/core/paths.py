from __future__ import annotations

import os
from pathlib import Path


def lmts_home() -> Path:
    value = os.environ.get('LMTS_HOME', '').strip()
    root = Path(value).expanduser() if value else Path.home() / '.lmts'
    return root.resolve()


def lmts_path(*parts: str) -> Path:
    return lmts_home().joinpath(*parts)


SETTINGS_PATH = lmts_path('settings.json')
SYSTEM_PROFILE_PATH = lmts_path('system-profile.json')
RUNTIME_TARGETS_PATH = lmts_path('runtime-targets.json')
RUNTIME_SECRETS_PATH = lmts_path('runtime-secrets.json')
FTP_PROFILES_PATH = lmts_path('ftp-profiles.json')
REPORT_PROFILES_PATH = lmts_path('report-profiles.json')
SHORTCUT_SETTINGS_PATH = lmts_path('shortcuts.json')
AUTH_SESSION_PATH = lmts_path('auth-session.json')
AUTH_SESSION_SECRET_PATH = lmts_path('auth-session.secret')
