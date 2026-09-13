from pathlib import Path

from lmts.core.workspace import Workspace
from lmts.core.workspace_protocol import execute_workspace_action


def test_workspace_protocol_read_write_finish(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    workspace.stage_input("task.txt", "hello")
    read = execute_workspace_action(workspace, {"action": "read", "mount": "input", "path": "task.txt"})
    assert read["content"] == "hello"
    execute_workspace_action(workspace, {"action": "write", "mount": "output", "path": "a.txt", "content": "ok"})
    assert (workspace.output_root / "a.txt").read_text() == "ok"
    finish = execute_workspace_action(workspace, {"action": "finish", "summary": "done"})
    assert finish["finished"] is True
