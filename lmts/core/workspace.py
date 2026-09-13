from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    allow_delete: bool = False
    max_write_bytes: int = 16 * 1024 * 1024


@dataclass(slots=True)
class WorkspaceTrace:
    operations: list[dict[str, object]] = field(default_factory=list)

    def add(self, operation: str, path: str, **details: object) -> None:
        self.operations.append({"operation": operation, "path": path, **details})


class Workspace:
    """Bounded workspace with immutable input and isolated work/output roots."""

    def __init__(self, root: Path, *, policy: WorkspacePolicy | None = None) -> None:
        self.root = root.expanduser().resolve()
        self.input_root = self.root / "input"
        self.work_root = self.root / "work"
        self.output_root = self.root / "output"
        self.policy = policy or WorkspacePolicy()
        self.trace = WorkspaceTrace()
        for path in (self.input_root, self.work_root, self.output_root):
            path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, mount: str, relative: str) -> Path:
        roots = {"input": self.input_root, "work": self.work_root, "output": self.output_root}
        if mount not in roots:
            raise ValueError(f"unknown workspace mount: {mount}")
        root = roots[mount]
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("workspace path escapes mount")
        return candidate

    def list(self, mount: str, relative: str = ".") -> list[str]:
        path = self._resolve(mount, relative)
        if not path.is_dir():
            raise NotADirectoryError(path)
        items = sorted(child.name for child in path.iterdir())
        self.trace.add("list", f"{mount}/{relative}", count=len(items))
        return items

    def tree(self, mount: str, relative: str = ".") -> list[str]:
        root = self._resolve(mount, relative)
        if not root.exists():
            raise FileNotFoundError(root)
        lines = [str(path.relative_to(root)) for path in sorted(root.rglob("*"))]
        self.trace.add("tree", f"{mount}/{relative}", count=len(lines))
        return lines

    def read(self, mount: str, relative: str) -> str:
        path = self._resolve(mount, relative)
        text = path.read_text(encoding="utf-8")
        self.trace.add("read", f"{mount}/{relative}", bytes=len(text.encode("utf-8")))
        return text

    def write(self, mount: str, relative: str, content: str) -> None:
        if mount == "input":
            raise PermissionError("input workspace is read-only")
        payload = content.encode("utf-8")
        if len(payload) > self.policy.max_write_bytes:
            raise ValueError("workspace write exceeds max_write_bytes")
        path = self._resolve(mount, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        self.trace.add("write", f"{mount}/{relative}", bytes=len(payload))

    def delete(self, mount: str, relative: str) -> None:
        if mount == "input":
            raise PermissionError("input workspace is read-only")
        if not self.policy.allow_delete:
            raise PermissionError("workspace delete disabled by policy")
        path = self._resolve(mount, relative)
        if path.is_dir():
            raise IsADirectoryError(path)
        path.unlink()
        self.trace.add("delete", f"{mount}/{relative}")
