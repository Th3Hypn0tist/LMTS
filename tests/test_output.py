from pathlib import Path

import pytest

from lmts.tools.output import DiskOutputTarget, write_files


def test_disk_output_writes_relative_tree(tmp_path: Path) -> None:
    written = write_files(
        DiskOutputTarget(tmp_path / 'www'),
        {'public/index.html': '<h1>LMTS</h1>', 'config/db.php': '<?php'},
    )
    assert len(written) == 2
    assert (tmp_path / 'www/public/index.html').read_text() == '<h1>LMTS</h1>'
    assert (tmp_path / 'www/config/db.php').read_text() == '<?php'


def test_output_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_files(DiskOutputTarget(tmp_path), {'../escape': 'no'})
