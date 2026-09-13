from pathlib import Path

from lmts.tools.ftp_profiles import FTPProfile, FTPProfiles, load_ftp_profiles, save_ftp_profiles


def test_ftp_profiles_round_trip(tmp_path: Path) -> None:
    path = tmp_path / '.lmts' / 'ftp-profiles.json'
    profile = FTPProfile(
        name='server',
        host='192.0.2.10',
        username='salanimi',
        password='secret',
        root='/home/www/lmts',
    )
    save_ftp_profiles(FTPProfiles(profiles=(profile,)), path)
    loaded = load_ftp_profiles(path)
    assert loaded.profiles == (profile,)
    assert loaded.profiles[0].root == '/home/www/lmts'
