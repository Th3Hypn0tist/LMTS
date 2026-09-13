from pathlib import Path

from lmts.view.shortcut_settings import (
    load_shortcut_overrides,
    normalise_sequence_text,
    save_shortcut_overrides,
)


def test_shortcut_sequence_text_is_normalised() -> None:
    assert normalise_sequence_text('ESC escape Q') == ('esc', 'esc', 'q')


def test_shortcut_overrides_round_trip(tmp_path: Path) -> None:
    path = tmp_path / '.lmts' / 'shortcuts.json'
    saved = {
        'profile.cpu': ('z',),
        'nav.back': ('esc', 'esc'),
    }
    save_shortcut_overrides(saved, path)
    assert load_shortcut_overrides(path) == saved
