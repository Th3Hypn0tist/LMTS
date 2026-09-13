from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TabDefinition:
    id: str
    label: str
    parent: str | None = None
    shortcut: str | None = None
    order: int = 0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError('tab id must not be empty')
        if not self.label.strip():
            raise ValueError('tab label must not be empty')
        if self.parent == self.id:
            raise ValueError('tab cannot be its own parent')
        if self.shortcut is not None and not self.shortcut.strip():
            raise ValueError('tab shortcut must not be empty')


class TabRegistry:
    """Recursive tab tree. Any tab may own child tabs."""

    def __init__(self, definitions: Iterable[TabDefinition] = ()) -> None:
        self._definitions: dict[str, TabDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: TabDefinition) -> TabDefinition:
        if definition.id in self._definitions:
            raise ValueError(f'duplicate tab id: {definition.id}')
        if definition.parent is not None and definition.parent not in self._definitions:
            raise ValueError(f'unknown parent tab: {definition.parent}')
        if definition.shortcut is not None:
            for sibling in self.children(definition.parent):
                if sibling.shortcut == definition.shortcut:
                    raise ValueError(
                        f'duplicate tab shortcut under {definition.parent or "<root>"}: '
                        f'{definition.shortcut}'
                    )
        self._definitions[definition.id] = definition
        return definition

    def get(self, tab_id: str) -> TabDefinition:
        try:
            return self._definitions[tab_id]
        except KeyError as exc:
            raise KeyError(f'unknown tab: {tab_id}') from exc

    def children(self, parent: str | None = None) -> tuple[TabDefinition, ...]:
        return tuple(
            sorted(
                (item for item in self._definitions.values() if item.parent == parent),
                key=lambda item: (item.order, item.label.casefold(), item.id),
            )
        )

    def parent(self, tab_id: str) -> TabDefinition | None:
        definition = self.get(tab_id)
        return self.get(definition.parent) if definition.parent is not None else None

    def path(self, tab_id: str) -> tuple[TabDefinition, ...]:
        output: list[TabDefinition] = []
        seen: set[str] = set()
        current = self.get(tab_id)
        while True:
            if current.id in seen:
                raise ValueError(f'tab cycle detected at {current.id}')
            seen.add(current.id)
            output.append(current)
            if current.parent is None:
                break
            current = self.get(current.parent)
        output.reverse()
        return tuple(output)

    def resolve_child_shortcut(self, parent: str | None, shortcut: str) -> TabDefinition | None:
        for child in self.children(parent):
            if child.shortcut == shortcut:
                return child
        return None

    def descendants(self, tab_id: str) -> tuple[TabDefinition, ...]:
        output: list[TabDefinition] = []
        for child in self.children(tab_id):
            output.append(child)
            output.extend(self.descendants(child.id))
        return tuple(output)
