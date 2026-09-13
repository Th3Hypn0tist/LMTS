from pathlib import Path

import pytest

from lmts.core.workspace import Workspace


def test_workspace_blocks_input_writes(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    with pytest.raises(PermissionError):
        workspace.write("input", "x.txt", "no")


def test_workspace_blocks_path_escape(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.read("input", "../outside.txt")


def test_workspace_writes_and_traces_output(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    workspace.write("output", "pkg/main.py", "print('ok')\n")
    assert workspace.read("output", "pkg/main.py") == "print('ok')\n"
    assert [item["operation"] for item in workspace.trace.operations] == ["write", "read"]
