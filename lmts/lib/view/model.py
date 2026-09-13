from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ViewItem:
    key: str
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class ViewFrame:
    title: str
    status: str
    lines: tuple[str, ...]
    items: tuple[ViewItem, ...] = field(default_factory=tuple)

    def text(self) -> str:
        body = "\n".join(self.lines)
        return f"{self.title}\n{self.status}\n\n{body}".rstrip() + "\n"
