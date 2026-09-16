"""Host-neutral view primitives."""

from .curses_host import CursesViewHost
from .events import UIEvent, UIEventBus
from .layout import LayoutPane
from .modals import ModalManager, ModalState
from .model import ViewFrame, ViewItem
from .path_dialog import choose_directory
from .preview_dialog import choose_with_preview
from .registry_split_host import RegistrySplitCursesViewHost
from .shortcut_registry import ShortcutDefinition, ShortcutMatch, ShortcutRegistry
from .split_host import SplitCursesViewHost
from .tab_registry import TabDefinition, TabRegistry

__all__ = [
    "CursesViewHost",
    "SplitCursesViewHost",
    "RegistrySplitCursesViewHost",
    "LayoutPane",
    "ViewFrame",
    "ViewItem",
    "choose_directory",
    "choose_with_preview",
    "UIEvent",
    "UIEventBus",
    "ModalManager",
    "ModalState",
    "ShortcutDefinition",
    "ShortcutMatch",
    "ShortcutRegistry",
    "TabDefinition",
    "TabRegistry",
]
