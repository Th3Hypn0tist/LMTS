from __future__ import annotations

from dataclasses import replace

from lmts.lib.view import ShortcutDefinition, ShortcutRegistry, TabDefinition, TabRegistry


TAB_REGISTRY = TabRegistry(
    [
        TabDefinition("root", "AIGM LMTS", parent=None, order=0),
        TabDefinition("profile", "Profile", parent="root", shortcut="1", order=10),
        TabDefinition("benchmark", "Benchmark", parent="root", shortcut="2", order=20),
        TabDefinition("deep", "Deep", parent="benchmark", order=21),
        TabDefinition("cw_bench", "CW Bench", parent="deep", order=22),
        TabDefinition("downloader", "Model Downloader", parent="root", shortcut="3", order=30),
        TabDefinition("settings", "Settings", parent="root", shortcut="4", order=40),
    ]
)


DEFAULT_SHORTCUTS = (
    ShortcutDefinition("tab.profile", ("1",), "Profile", "Tabs", order=10),
    ShortcutDefinition("tab.benchmark", ("2",), "Benchmark", "Tabs", order=20),
    ShortcutDefinition("tab.downloader", ("3",), "Model Downloader", "Tabs", order=30),
    ShortcutDefinition("tab.settings", ("4",), "Settings", "Tabs", order=40),
    ShortcutDefinition("nav.back", ("esc", "esc"), "Back", "Navigation", order=900),
    ShortcutDefinition("scroll.up", ("up",), "Scroll up", "Navigation", order=910),
    ShortcutDefinition("scroll.down", ("down",), "Scroll down", "Navigation", order=920),
    ShortcutDefinition("app.quit", ("q", "q", "q"), "Quit", "System", order=930),

    ShortcutDefinition("profile.cpu", ("z",), "Test CPU", "Profile", scope="profile", order=100),
    ShortcutDefinition("profile.memory", ("x",), "Test MEM", "Profile", scope="profile", order=110),
    ShortcutDefinition("profile.gpu", ("c",), "Test GPU", "Profile", scope="profile", order=120),
    ShortcutDefinition("profile.npu", ("v",), "Test NPU", "Profile", scope="profile", order=130),
    ShortcutDefinition("profile.scan", ("p",), "Profile system", "Profile", scope="profile", order=140),

    ShortcutDefinition("benchmark.quick", ("z",), "Quick", "Benchmark", scope="benchmark", order=80),
    ShortcutDefinition("benchmark.moderate", ("x",), "Moderate", "Benchmark", scope="benchmark", order=90),
    ShortcutDefinition("benchmark.deep", ("c",), "Deep", "Benchmark", scope="benchmark", order=100),
    ShortcutDefinition("targets", ("m",), "Targets", "Benchmark", scope="benchmark", order=110),
    ShortcutDefinition("tests", ("t",), "Matrix", "Benchmark", scope="benchmark", order=120),
    ShortcutDefinition("test.add", ("n",), "Add test", "Benchmark", scope="benchmark", order=130),
    ShortcutDefinition("test.remove", ("d",), "Remove test", "Benchmark", scope="benchmark", order=140),
    ShortcutDefinition("run.selected", ("r",), "Run", "Benchmark", scope="benchmark", order=150),
    ShortcutDefinition("run.all", ("a",), "Run all", "Benchmark", scope="benchmark", order=160),
    ShortcutDefinition("results", ("v",), "Results", "Benchmark", scope="benchmark", order=170),
    ShortcutDefinition("benchmark.compare", ("b",), "Compare targets", "Benchmark", scope="benchmark", order=180),
    ShortcutDefinition("benchmark.publish", ("u",), "Publish report", "Benchmark", scope="benchmark", order=190),
    ShortcutDefinition("errors", ("e",), "Errors", "Benchmark", scope="benchmark", order=200),
    ShortcutDefinition("refresh", ("f",), "Refresh", "Benchmark", scope="benchmark", order=210),
    ShortcutDefinition("benchmark.console", ("+",), "Console", "Benchmark", scope="benchmark", order=220),

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
    ShortcutDefinition("downloader.download", ("d",), "Download model", "Model Downloader", scope="downloader", order=110),
    ShortcutDefinition("downloader.progress", ("p",), "Download progress", "Model Downloader", scope="downloader", order=120),
    ShortcutDefinition("downloader.refresh", ("r",), "Refresh", "Model Downloader", scope="downloader", order=130),
    ShortcutDefinition("downloader.cancel", ("c",), "Cancel download", "Model Downloader", scope="downloader", order=140),

    ShortcutDefinition("settings.output", ("o",), "Output folder", "Settings", scope="settings", order=100),
    ShortcutDefinition("settings.server", ("i",), "Server setup", "Settings", scope="settings", order=110),
    ShortcutDefinition("settings.mysql", ("m",), "MySQL", "Settings", scope="settings", order=120),
    ShortcutDefinition("settings.ftp", ("f",), "FTP", "Settings", scope="settings", order=130),
    ShortcutDefinition("settings.report", ("r",), "Report API", "Settings", scope="settings", order=140),
    ShortcutDefinition("settings.targets", ("t",), "Runtime targets", "Settings", scope="settings", order=150),
    ShortcutDefinition("settings.shortcuts", ("k",), "Shortcut editor", "Settings", scope="settings", order=160),
)


def build_shortcut_registry(overrides: dict[str, tuple[str, ...]] | None = None) -> ShortcutRegistry:
    overrides = {} if overrides is None else overrides
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
