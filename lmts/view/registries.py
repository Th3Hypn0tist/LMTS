from __future__ import annotations

from dataclasses import replace

from lmts.lib.view import ShortcutDefinition, ShortcutRegistry, TabDefinition, TabRegistry


TAB_REGISTRY = TabRegistry(
    [
        TabDefinition("root", "AIGM LMTS", parent=None, order=0),
        TabDefinition("profile", "Profile", parent="root", shortcut="1", order=10),
        TabDefinition("benchmark", "Benchmark", parent="root", shortcut="2", order=20),
        TabDefinition("settings", "Settings", parent="root", shortcut="3", order=30),
    ]
)


DEFAULT_SHORTCUTS = (
    ShortcutDefinition("tab.profile", ("1",), "Profile", "Tabs", order=10),
    ShortcutDefinition("tab.benchmark", ("2",), "Benchmark", "Tabs", order=20),
    ShortcutDefinition("tab.settings", ("3",), "Settings", "Tabs", order=30),
    ShortcutDefinition("nav.back", ("esc", "esc"), "Back", "Navigation", order=900),
    ShortcutDefinition("scroll.up", ("up",), "Scroll up", "Navigation", order=910),
    ShortcutDefinition("scroll.down", ("down",), "Scroll down", "Navigation", order=920),
    ShortcutDefinition("app.quit", ("q", "q", "q"), "Quit", "System", order=930),

    ShortcutDefinition("profile.cpu", ("z",), "Test CPU", "Profile", scope="profile", order=100),
    ShortcutDefinition("profile.memory", ("x",), "Test MEM", "Profile", scope="profile", order=110),
    ShortcutDefinition("profile.gpu", ("c",), "Test GPU", "Profile", scope="profile", order=120),
    ShortcutDefinition("profile.npu", ("v",), "Test NPU", "Profile", scope="profile", order=130),
    ShortcutDefinition("profile.scan", ("p",), "Profile system", "Profile", scope="profile", order=140),

    ShortcutDefinition("targets", ("m",), "Targets", "Benchmark", scope="benchmark", order=100),
    ShortcutDefinition("tests", ("t",), "Matrix", "Benchmark", scope="benchmark", order=110),
    ShortcutDefinition("test.add", ("n",), "Add test", "Benchmark", scope="benchmark", order=120),
    ShortcutDefinition("test.remove", ("d",), "Remove test", "Benchmark", scope="benchmark", order=130),
    ShortcutDefinition("run.selected", ("r",), "Run", "Benchmark", scope="benchmark", order=140),
    ShortcutDefinition("run.all", ("a",), "Run all", "Benchmark", scope="benchmark", order=150),
    ShortcutDefinition("results", ("v",), "Results", "Benchmark", scope="benchmark", order=160),
    ShortcutDefinition("benchmark.publish", ("u",), "Publish report", "Benchmark", scope="benchmark", order=170),
    ShortcutDefinition("cancel", ("c",), "Cancel", "Benchmark", scope="benchmark", order=180),
    ShortcutDefinition("errors", ("e",), "Errors", "Benchmark", scope="benchmark", order=190),
    ShortcutDefinition("refresh", ("x",), "Refresh", "Benchmark", scope="benchmark", order=200),

    ShortcutDefinition("settings.output", ("o",), "Output folder", "Settings", scope="settings", order=100),
    ShortcutDefinition("settings.server", ("i",), "Server setup", "Settings", scope="settings", order=110),
    ShortcutDefinition("settings.mysql", ("m",), "MySQL", "Settings", scope="settings", order=120),
    ShortcutDefinition("settings.ftp", ("f",), "FTP", "Settings", scope="settings", order=130),
    ShortcutDefinition("settings.report", ("r",), "Report API", "Settings", scope="settings", order=140),
    ShortcutDefinition("settings.shortcuts", ("k",), "Shortcut editor", "Settings", scope="settings", order=150),
)


def build_shortcut_registry(
    overrides: dict[str, tuple[str, ...]] | None = None,
) -> ShortcutRegistry:
    overrides = overrides or {}
    known_actions = {definition.action for definition in DEFAULT_SHORTCUTS}
    unknown = sorted(set(overrides) - known_actions)
    if unknown:
        raise ValueError(f"unknown shortcut action override(s): {', '.join(unknown)}")

    definitions = [
        replace(definition, sequence=overrides.get(definition.action, definition.sequence))
        for definition in DEFAULT_SHORTCUTS
    ]

    for index, left in enumerate(definitions):
        for right in definitions[index + 1 :]:
            scopes_overlap = (
                left.scope == right.scope
                or left.scope == "global"
                or right.scope == "global"
            )
            if not scopes_overlap:
                continue
            common = min(len(left.sequence), len(right.sequence))
            if left.sequence[:common] == right.sequence[:common]:
                raise ValueError(
                    f"ambiguous shortcuts: {left.action}={left.sequence_label} / "
                    f"{right.action}={right.sequence_label}"
                )

    return ShortcutRegistry(definitions)


SHORTCUT_REGISTRY = build_shortcut_registry()
