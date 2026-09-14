from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LayoutPane:
    """One page-local view pane addressable by a Layout-mode numeric slot."""

    slot: int
    label: str
    render: Callable[[], Sequence[str]]
    title: str = ""
    primary: bool = False
    default_visible: bool = True
    auto_hide_empty: bool = False
    follow_tail: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.slot <= 9:
            raise ValueError("layout pane slot must be in range 1..9")
        if not self.label.strip():
            raise ValueError("layout pane label must be non-empty")
