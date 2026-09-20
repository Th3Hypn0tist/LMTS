from __future__ import annotations

from dataclasses import replace

from lmts.lib.view import ShortcutDefinition, ShortcutRegistry, TabDefinition, TabRegistry


TAB_REGISTRY = TabRegistry(
    [
        TabDefinition("root", "AIGM LMTS", parent=None, order=0),
        TabDefinition("benchmark", "Benchmark", parent="root", shortcut="1", order=10),
        TabDefinition("deep", "Deep", parent="benchmark", order=11),
        TabDefinition("cw_bench", "CW Bench", parent="deep", order=12),
        TabDefinition("stats", "Stats", parent="root", shortcut="2", order=20),
        TabDefinition("downloader", "Model Downloader", parent="root", shortcut="3", order=30),
        TabDefinition("profile", "Profiling", parent="root", shortcut="9", order=90),
        TabDefinition("settings", "Settings", parent="root", shortcut="0", order=100),
        TabDefinition("user", "User", parent="settings", order=91),
    ]
)


DEFAULT_SHORTCUTS = (
    ShortcutDefinition("tab.benchmark", ("1",), "Benchmark", "Tabs", order=10),
    ShortcutDefinition("tab.stats", ("2",), "Stats", "Tabs", order=20),
    ShortcutDefinition("tab.downloader", ("3",), "Model Downloader", "Tabs", order=30),
    ShortcutDefinition("tab.profile", ("9",), "Profiling", "Tabs", order=90),
    ShortcutDefinition("tab.settings", ("0",), "Settings", "Tabs", order=100),
    ShortcutDefinition("app.help", ("f1",), "Help", "Help", order=890),
    ShortcutDefinition("nav.back", ("esc",), "Back", "Navigation", order=900),
    ShortcutDefinition("scroll.up", ("up",), "Scroll up", "Navigation", order=910),
    ShortcutDefinition("scroll.down", ("down",), "Scroll down", "Navigation", order=920),
    ShortcutDefinition("app.quit", ("q", "q", "q"), "Quit", "System", order=930),

    ShortcutDefinition("profile.scan", ("p",), "Profile system", "Profiling", scope="profile", order=100),

    ShortcutDefinition("stats.refresh", ("f",), "Refresh", "Stats", scope="stats", order=100),
    ShortcutDefinition("user.refresh", ("f",), "Refresh", "User", scope="user", order=100),

    ShortcutDefinition("benchmark.tests", ("t",), "Tests", "Benchmark", scope="benchmark", order=100),
    ShortcutDefinition("benchmark.targets", ("m",), "Targets", "Benchmark", scope="benchmark", order=110),
    ShortcutDefinition("benchmark.run", ("r",), "Run", "Benchmark", scope="benchmark", order=120),
    ShortcutDefinition("benchmark.output", ("o",), "Output", "Benchmark", scope="benchmark", order=130),
    ShortcutDefinition("benchmark.refresh", ("f",), "Refresh", "Benchmark", scope="benchmark", order=140),

    ShortcutDefinition("deep.cw_bench", ("z",), "CW Bench", "Deep", scope="deep", order=100),
    ShortcutDefinition("deep.run", ("x",), "Run Deep suite", "Deep", scope="deep", order=110),
    ShortcutDefinition("deep.results", ("c",), "Results", "Deep", scope="deep", order=120),

    ShortcutDefinition("cw.source", ("z",), "CW source", "CW Bench", scope="cw_bench", order=100),
    ShortcutDefinition("cw.language", ("x",), "Output language", "CW Bench", scope="cw_bench", order=110),
    ShortcutDefinition("cw.models", ("c",), "Models", "CW Bench", scope="cw_bench", order=120),
    ShortcutDefinition("cw.run", ("v",), "Run CW Bench", "CW Bench", scope="cw_bench", order=130),
    ShortcutDefinition("cw.results", ("b",), "Results", "CW Bench", scope="cw_bench", order=140),
    ShortcutDefinition("cw.cancel", ("n",), "Cancel", "CW Bench", scope="cw_bench", order=150),

    ShortcutDefinition("downloader.module", ("m",), "Select module", "Model Downloader", scope="downloader", order=100),
    ShortcutDefinition("downloader.download", ("d",), "Queue models", "Model Downloader", scope="downloader", order=110),
    ShortcutDefinition("downloader.delete", ("x",), "Delete model", "Model Downloader", scope="downloader", order=120),
    ShortcutDefinition("downloader.progress", ("p",), "Download progress", "Model Downloader", scope="downloader", order=130),
    ShortcutDefinition("downloader.refresh", ("r",), "Refresh", "Model Downloader", scope="downloader", order=140),
    ShortcutDefinition("downloader.cancel", ("c",), "Cancel download", "Model Downloader", scope="downloader", order=150),

    ShortcutDefinition("settings.user", ("u",), "User", "Settings", scope="settings", order=90),
    ShortcutDefinition("settings.output", ("o",), "Output folder", "Settings", scope="settings", order=100),
    ShortcutDefinition("settings.report_output", ("r",), "Report output", "Settings", scope="settings", order=110),
    ShortcutDefinition("settings.targets", ("t",), "Runtime targets", "Settings", scope="settings", order=130),
    ShortcutDefinition("settings.shortcuts", ("k",), "Shortcut editor", "Settings", scope="settings", order=140),
)


LEGACY_SHORTCUT_ACTIONS = frozenset({'settings.server', 'settings.mysql', 'settings.ftp', 'settings.report'})


def build_shortcut_registry(overrides: dict[str, tuple[str, ...]] | None = None) -> ShortcutRegistry:
    overrides = {} if overrides is None else {key: value for key, value in overrides.items() if key not in LEGACY_SHORTCUT_ACTIONS}
    known_actions = {definition.action for definition in DEFAULT_SHORTCUTS}
    unknown = sorted(set(overrides) - known_actions)
    if unknown:
        raise ValueError(f"unknown shortcut action override(s): {', '.join(unknown)}")

    definitions = [replace(definition, sequence=overrides.get(definition.action, definition.sequence)) for definition in DEFAULT_SHORTCUTS]
    for index, left in enumerate(definitions):
        for right in definitions[index + 1 :]:
            scopes_overlap = left.scope == right.scope or left.scope == "global" or right.scope == "global"
            if not scopes_overlap:
                continue
            common = min(len(left.sequence), len(right.sequence))
            if left.sequence[:common] == right.sequence[:common]:
                raise ValueError(f"ambiguous shortcuts: {left.action}={left.sequence_label} / {right.action}={right.sequence_label}")
    return ShortcutRegistry(definitions)


SHORTCUT_REGISTRY = build_shortcut_registry()
