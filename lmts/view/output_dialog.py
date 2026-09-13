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
    name = _single_line(host, stdscr, 'FTP profile name')
    if name is None:
        return None
    host_name = _single_line(host, stdscr, 'FTP host')
    if host_name is None:
        return None
    port_text = _single_line(host, stdscr, 'FTP port', initial='21')
    if port_text is None:
        return None
    try:
        port = int(port_text)
    except ValueError:
        host.message = 'FTP port must be an integer'
        return None
    username = _single_line(host, stdscr, 'FTP username')
    if username is None:
        return None
    password = _single_line(host, stdscr, 'FTP password')
    if password is None:
        return None
    root = _single_line(host, stdscr, 'FTP web root', initial='/home/www/lmts')
    if root is None:
        return None
    web_base_url = _single_line(
        host,
        stdscr,
        'Benchmark web URL',
        initial=f'http://{host_name}/benchmark/',
    )
    if web_base_url is None:
        return None

    profile = FTPProfile(
        name=name,
        host=host_name,
        port=port,
        username=username,
        password=password,
        root=root,
        web_base_url=web_base_url,
    )
    profiles = load_ftp_profiles(store_path).upsert(profile)
    save_ftp_profiles(profiles, store_path)
    host.message = f'FTP profile saved: {profile.name}'
    return profile


def choose_ftp_profile(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    store_path: Path = DEFAULT_FTP_PROFILES_PATH,
) -> FTPProfile | None:
    profiles = load_ftp_profiles(store_path)
    options = ['[New FTP profile]', *(profile.name for profile in profiles.profiles)]
    chosen = host.choose(stdscr, 'FTP profile', options)
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
        options = ['New FTP profile', *(f'Delete  {profile.name}' for profile in profiles.profiles)]
        chosen = host.choose(stdscr, 'FTP profiles', options)
        if chosen is None:
            return
        if chosen == 0:
            create_ftp_profile(host, stdscr, store_path=store_path)
            continue
        profile = profiles.profiles[chosen - 1]
        confirm = host.choose(stdscr, f'Delete FTP profile {profile.name}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_ftp_profiles(profiles.remove(profile.name), store_path)
            host.message = f'FTP profile deleted: {profile.name}'


def choose_output_target(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    disk_initial: str | Path = '.',
) -> OutputTarget | None:
    chosen = host.choose(stdscr, 'Output', ['Disk', 'FTP'])
    if chosen is None:
        return None
    if chosen == 0:
        directory = choose_directory(host, stdscr, 'Output folder', initial=disk_initial)
        return None if directory is None else DiskOutputTarget(directory)
    profile = choose_ftp_profile(host, stdscr)
    return None if profile is None else FTPOutputTarget(profile)
