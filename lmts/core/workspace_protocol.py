from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .models import NormalizedResponse
from .workspace import Workspace


class WorkspaceProtocolError(ValueError):
    pass


@dataclass(slots=True)
class WorkspaceProtocolResult:
    finished: bool = False
    summary: str | None = None
    steps: int = 0
    responses: list[NormalizedResponse] = field(default_factory=list)


def _parse_action(text: str) -> dict[str, Any]:
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    try:
        action = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkspaceProtocolError(f"invalid workspace action JSON: {exc}") from exc
    if not isinstance(action, dict):
        raise WorkspaceProtocolError("workspace action must be a JSON object")
    return action


def _require_string(action: dict[str, Any], name: str, *, default: str | None = None) -> str:
    value = action.get(name, default)
    if not isinstance(value, str) or not value:
        raise WorkspaceProtocolError(f"workspace action field must be a non-empty string: {name}")
    return value


def execute_workspace_action(workspace: Workspace, action: dict[str, Any]) -> dict[str, Any]:
    operation = _require_string(action, "action").lower()
    if operation == "list":
        mount = _require_string(action, "mount")
        path = action.get("path", ".")
        if not isinstance(path, str):
            raise WorkspaceProtocolError("path must be a string")
        return {"ok": True, "action": operation, "items": workspace.list(mount, path)}
    if operation == "tree":
        mount = _require_string(action, "mount")
        path = action.get("path", ".")
        if not isinstance(path, str):
            raise WorkspaceProtocolError("path must be a string")
        return {"ok": True, "action": operation, "items": workspace.tree(mount, path)}
    if operation == "read":
        mount = _require_string(action, "mount")
        path = _require_string(action, "path")
        return {"ok": True, "action": operation, "content": workspace.read(mount, path)}
    if operation == "write":
        mount = _require_string(action, "mount")
        path = _require_string(action, "path")
        content = action.get("content")
        if not isinstance(content, str):
            raise WorkspaceProtocolError("content must be a string")
        workspace.write(mount, path, content)
        return {"ok": True, "action": operation, "path": f"{mount}/{path}"}
    if operation == "mkdir":
        mount = _require_string(action, "mount")
        path = _require_string(action, "path")
        workspace.mkdir(mount, path)
        return {"ok": True, "action": operation, "path": f"{mount}/{path}"}
    if operation == "finish":
        summary = action.get("summary")
        if summary is not None and not isinstance(summary, str):
            raise WorkspaceProtocolError("summary must be a string")
        return {"ok": True, "action": operation, "finished": True, "summary": summary}
    raise WorkspaceProtocolError(f"unsupported workspace action: {operation}")


class WorkspaceProtocolSession:
    """Text-mediated bounded workspace protocol for models without native tool calling."""

    PROTOCOL = """LMTS Workspace Protocol v1.
Reply with exactly one JSON object per turn and no prose.
Available actions:
{"action":"list","mount":"input|work|output","path":"."}
{"action":"tree","mount":"input|work|output","path":"."}
{"action":"read","mount":"input|work|output","path":"relative/path"}
{"action":"mkdir","mount":"work|output","path":"relative/path"}
{"action":"write","mount":"work|output","path":"relative/path","content":"text"}
{"action":"finish","summary":"optional summary"}
The input mount is read-only. Do not use absolute paths or parent traversal.
"""

    def __init__(self, *, max_steps: int = 64) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.max_steps = max_steps

    def run(self, context: Any, task: str) -> WorkspaceProtocolResult:
        transcript: list[str] = [self.PROTOCOL, "TASK:", task]
        result = WorkspaceProtocolResult()
        for step in range(1, self.max_steps + 1):
            prompt = "\n\n".join(transcript + ["Return the next workspace action JSON now."])
            response = context.generate(prompt)
            result.responses.append(response)
            action = _parse_action(response.text)
            outcome = execute_workspace_action(context.workspace, action)
            result.steps = step
            transcript.append(f"MODEL_ACTION_{step}:\n{json.dumps(action, ensure_ascii=False)}")
            transcript.append(f"LMTS_RESULT_{step}:\n{json.dumps(outcome, ensure_ascii=False)}")
            if outcome.get("finished") is True:
                result.finished = True
                result.summary = outcome.get("summary") if isinstance(outcome.get("summary"), str) else None
                return result
        raise WorkspaceProtocolError(f"workspace protocol exceeded max_steps={self.max_steps}")
