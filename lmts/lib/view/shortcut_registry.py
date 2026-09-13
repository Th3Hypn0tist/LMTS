from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


MatchKind = Literal['none', 'prefix', 'exact']


@dataclass(frozen=True, slots=True)
class ShortcutDefinition:
    action: str
    sequence: tuple[str, ...]
    label: str
    topic: str
    scope: str = 'global'
    order: int = 0

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError('shortcut action must not be empty')
        if not self.sequence or any(not token for token in self.sequence):
            raise ValueError('shortcut sequence must contain at least one non-empty token')
        if not self.label.strip():
            raise ValueError('shortcut label must not be empty')
        if not self.topic.strip():
            raise ValueError('shortcut topic must not be empty')
        if not self.scope.strip():
            raise ValueError('shortcut scope must not be empty')

    @property
    def sequence_label(self) -> str:
        labels = {
            'esc': 'Esc',
            'up': 'Up',
            'down': 'Down',
            'left': 'Left',
            'right': 'Right',
            'pgup': 'PgUp',
            'pgdn': 'PgDn',
            'enter': 'Enter',
            'space': 'Space',
        }
        return ' '.join(labels.get(token, token) for token in self.sequence)


@dataclass(frozen=True, slots=True)
class ShortcutMatch:
    kind: MatchKind
    buffer: tuple[str, ...] = ()
    shortcut: ShortcutDefinition | None = None


class ShortcutRegistry:
    """Topic-grouped, scope-aware registry for application key sequences."""

    def __init__(self, definitions: Iterable[ShortcutDefinition] = ()) -> None:
        self._definitions: list[ShortcutDefinition] = []
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ShortcutDefinition) -> ShortcutDefinition:
        for current in self._definitions:
            scopes_overlap = (
                current.scope == definition.scope
                or current.scope == 'global'
                or definition.scope == 'global'
            )
            if scopes_overlap:
                common = min(len(current.sequence), len(definition.sequence))
                prefix_collision = current.sequence[:common] == definition.sequence[:common]
                if prefix_collision:
                    raise ValueError(
                        f'ambiguous shortcut sequences in overlapping scopes '
                        f'{current.scope}/{definition.scope}: '
                        f'{current.sequence_label} / {definition.sequence_label}'
                    )
            if current.action == definition.action and current.scope == definition.scope:
                raise ValueError(
                    f'duplicate shortcut action in scope {definition.scope}: {definition.action}'
                )
        self._definitions.append(definition)
        return definition

    def definitions(self, scopes: Iterable[str] = ('global',)) -> tuple[ShortcutDefinition, ...]:
        active = set(scopes)
        active.add('global')
        return tuple(
            sorted(
                (definition for definition in self._definitions if definition.scope in active),
                key=lambda item: (item.order, item.topic.casefold(), item.label.casefold(), item.action),
            )
        )

    def topics(self, scopes: Iterable[str] = ('global',)) -> tuple[tuple[str, tuple[ShortcutDefinition, ...]], ...]:
        grouped: dict[str, list[ShortcutDefinition]] = {}
        order: list[str] = []
        for definition in self.definitions(scopes):
            if definition.topic not in grouped:
                grouped[definition.topic] = []
                order.append(definition.topic)
            grouped[definition.topic].append(definition)
        return tuple((topic, tuple(grouped[topic])) for topic in order)

    def footer(self, scopes: Iterable[str] = ('global',)) -> str:
        groups: list[str] = []
        for topic, definitions in self.topics(scopes):
            labels = '  '.join(f'{item.sequence_label} {item.label}' for item in definitions)
            groups.append(f'{topic}: {labels}')
        return ' | '.join(groups)

    def match(
        self,
        buffer: tuple[str, ...],
        token: str,
        scopes: Iterable[str] = ('global',),
    ) -> ShortcutMatch:
        definitions = self.definitions(scopes)
        candidate = buffer + (token,)
        match = self._match_candidate(candidate, definitions)
        if match.kind != 'none' or not buffer:
            return match
        return self._match_candidate((token,), definitions)

    @staticmethod
    def _match_candidate(
        candidate: tuple[str, ...],
        definitions: tuple[ShortcutDefinition, ...],
    ) -> ShortcutMatch:
        exact: ShortcutDefinition | None = None
        has_longer = False
        for definition in definitions:
            if definition.sequence == candidate:
                exact = definition
            elif len(definition.sequence) > len(candidate) and definition.sequence[: len(candidate)] == candidate:
                has_longer = True
        if exact is not None and not has_longer:
            return ShortcutMatch('exact', (), exact)
        if exact is not None or has_longer:
            return ShortcutMatch('prefix', candidate, exact)
        return ShortcutMatch('none')
