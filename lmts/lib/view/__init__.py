"""Host-neutral view primitives."""

from .curses_host import CursesViewHost
from .model import ViewFrame, ViewItem
from .path_dialog import choose_directory
from .shortcut_registry import ShortcutDefinition, ShortcutMatch, ShortcutRegistry
from .split_host import SplitCursesViewHost
from .tab_registry import TabDefinition, TabRegistry

__all__ = [
    "CursesViewHost",
    "SplitCursesViewHost",
    "ViewFrame",
    "ViewItem",
    "choose_directory",
    "ShortcutDefinition",
    "ShortcutMatch",
    "ShortcutRegistry",
    "TabDefinition",
    "TabRegistry",
]
