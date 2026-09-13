from pathlib import Path

import pytest

from lmts.core.workspace import Workspace


def test_workspace_input_is_read_only(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    with pytest.raises(PermissionError):
        workspace.write("input", "x.txt", "no")


def test_workspace_stage_input_and_read(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    workspace.stage_input("x.txt", "yes")
    assert workspace.read("input", "x.txt") == "yes"


def test_workspace_write_and_escape_guard(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    workspace.write("output", "nested/a.txt", "ok")
    assert (workspace.output_root / "nested" / "a.txt").read_text() == "ok"
    with pytest.raises(ValueError):
        workspace.write("output", "../escape.txt", "no")


def test_workspace_delete_disabled(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    workspace.write("output", "a.txt", "ok")
    with pytest.raises(PermissionError):
        workspace.delete("output", "a.txt")
