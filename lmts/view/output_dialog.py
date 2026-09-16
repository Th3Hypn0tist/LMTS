from __future__ import annotations

import curses
from pathlib import Path

from lmts.lib.view import CursesViewHost, choose_directory
from lmts.tools.ftp_profiles import (
    DEFAULT_FTP_PROFILES_PATH,
    FTPProfile,
    load_ftp_profiles,
    save_ftp_profiles,
)
from lmts.tools.output import DiskOutputTarget, FTPOutputTarget, OutputTarget
from lmts.tools.report_profiles import (
    DEFAULT_REPORT_PROFILES_PATH,
    ReportProfile,
    load_report_profiles,
    save_report_profiles,
)


def _single_line(
    host: CursesViewHost,
    stdscr: curses.window,
    title: str,
    *,
    initial: str = '',
) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if value and '\n' not in value and '\r' not in value:
            return value
        host.message = f'{title}: enter one non-empty line'


def create_ftp_profile(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_FTP_PROFILES_PATH,
) -> FTPProfile | None:
    name = _single_line(host, stdscr, 'FTPS profile name')
    if name is None:
        return None
    host_name = _single_line(host, stdscr, 'FTPS host')
    if host_name is None:
        return None
    port_text = _single_line(host, stdscr, 'FTPS port', initial='21')
    if port_text is None:
        return None
    try:
        port = int(port_text)
    except ValueError:
        host.message = 'FTPS port must be an integer'
        return None
    username = _single_line(host, stdscr, 'FTPS username')
    if username is None:
        return None
    password_env = _single_line(host, stdscr, 'FTPS password environment variable')
    if password_env is None:
        return None
    root = _single_line(host, stdscr, 'FTPS target root')
    if root is None:
        return None

    profile = FTPProfile(
        name=name,
        host=host_name,
        port=port,
        username=username,
        password_env=password_env,
        root=root,
    )
    profiles = load_ftp_profiles(store_path).upsert(profile)
    save_ftp_profiles(profiles, store_path)
    host.message = f'FTPS profile saved: {profile.name} (secret: ${profile.password_env})'
    return profile


def choose_ftp_profile(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_FTP_PROFILES_PATH,
) -> FTPProfile | None:
    profiles = load_ftp_profiles(store_path)
    options = ['[New FTPS profile]', *(profile.name for profile in profiles.profiles)]
    chosen = host.choose(stdscr, 'FTPS profile', options)
    if chosen is None:
        return None
    if chosen == 0:
        return create_ftp_profile(host, stdscr, store_path=store_path)
    return profiles.profiles[chosen - 1]


def manage_ftp_profiles(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_FTP_PROFILES_PATH,
) -> None:
    while True:
        profiles = load_ftp_profiles(store_path)
        options = ['New FTPS profile', *(f'Delete  {profile.name}' for profile in profiles.profiles)]
        chosen = host.choose(stdscr, 'FTPS profiles', options)
        if chosen is None:
            return
        if chosen == 0:
            create_ftp_profile(host, stdscr, store_path=store_path)
            continue
        profile = profiles.profiles[chosen - 1]
        confirm = host.choose(stdscr, f'Delete FTPS profile {profile.name}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_ftp_profiles(profiles.remove(profile.name), store_path)
            host.message = f'FTPS profile deleted: {profile.name}'


def create_report_profile(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_REPORT_PROFILES_PATH,
) -> ReportProfile | None:
    name = _single_line(host, stdscr, 'Report profile name')
    if name is None:
        return None
    endpoint = _single_line(host, stdscr, 'Exact Report API endpoint', initial='http://127.0.0.1/api/report.php')
    if endpoint is None:
        return None
    publish_key = _single_line(host, stdscr, 'Report publish key', initial='lmts')
    if publish_key is None:
        return None
    profile = ReportProfile(name=name, endpoint=endpoint, publish_key=publish_key)
    profiles = load_report_profiles(store_path).upsert(profile)
    save_report_profiles(profiles, store_path)
    host.message = f'report profile saved: {profile.name}'
    return profile


def choose_report_profile(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_REPORT_PROFILES_PATH,
) -> ReportProfile | None:
    profiles = load_report_profiles(store_path)
    options = ['[New report profile]', *(profile.name for profile in profiles.profiles)]
    chosen = host.choose(stdscr, 'Report API profile', options)
    if chosen is None:
        return None
    if chosen == 0:
        return create_report_profile(host, stdscr, store_path=store_path)
    return profiles.profiles[chosen - 1]


def manage_report_profiles(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_REPORT_PROFILES_PATH,
) -> None:
    while True:
        profiles = load_report_profiles(store_path)
        options = ['New report profile', *(f'Delete  {profile.name}' for profile in profiles.profiles)]
        chosen = host.choose(stdscr, 'Report API profiles', options)
        if chosen is None:
            return
        if chosen == 0:
            create_report_profile(host, stdscr, store_path=store_path)
            continue
        profile = profiles.profiles[chosen - 1]
        confirm = host.choose(stdscr, f'Delete report profile {profile.name}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_report_profiles(profiles.remove(profile.name), store_path)
            host.message = f'report profile deleted: {profile.name}'


def choose_output_target(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    disk_initial: str | Path = '.',
) -> OutputTarget | None:
    chosen = host.choose(stdscr, 'Output', ['Disk', 'FTPS'])
    if chosen is None:
        return None
    if chosen == 0:
        directory = choose_directory(host, stdscr, 'Output folder', initial=disk_initial)
        return None if directory is None else DiskOutputTarget(directory)
    profile = choose_ftp_profile(host, stdscr)
    return None if profile is None else FTPOutputTarget(profile)
