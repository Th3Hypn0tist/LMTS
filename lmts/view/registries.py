from __future__ import annotations

from lmts.lib.view import ShortcutDefinition, ShortcutRegistry, TabDefinition, TabRegistry


TAB_REGISTRY = TabRegistry(
    [
        TabDefinition("root", "AIGM LMTS", parent=None, order=0),
        TabDefinition("profiler", "Profiler", parent="root", shortcut="1", order=10),
        TabDefinition("server", "Server tools", parent="root", shortcut="2", order=20),
        TabDefinition("benchmark", "Benchmark", parent="root", shortcut="3", order=30),
    ]
)


SHORTCUT_REGISTRY = ShortcutRegistry(
    [
        ShortcutDefinition("tab.profiler", ("1",), "Profiler", "Tabs", order=10),
        ShortcutDefinition("tab.server", ("2",), "Server tools", "Tabs", order=20),
        ShortcutDefinition("tab.benchmark", ("3",), "Benchmark", "Tabs", order=30),
        ShortcutDefinition("nav.back", ("esc", "esc"), "Back", "Navigation", order=40),
        ShortcutDefinition("scroll.up", ("up",), "Scroll up", "Navigation", order=50),
        ShortcutDefinition("scroll.down", ("down",), "Scroll down", "Navigation", order=60),
        ShortcutDefinition("settings", ("s",), "Settings", "System", order=70),
        ShortcutDefinition("app.quit", ("q", "q", "q"), "Quit", "System", order=80),
        ShortcutDefinition("profile.run", ("p",), "Profile system", "Profiler", scope="profiler", order=100),
        ShortcutDefinition("server.output", ("o",), "Output", "Server", scope="server", order=100),
        ShortcutDefinition("models", ("m",), "Models", "Benchmark", scope="benchmark", order=100),
        ShortcutDefinition("tests", ("t",), "Matrix", "Benchmark", scope="benchmark", order=110),
        ShortcutDefinition("test.add", ("n",), "Add test", "Benchmark", scope="benchmark", order=120),
        ShortcutDefinition("test.remove", ("d",), "Remove test", "Benchmark", scope="benchmark", order=130),
        ShortcutDefinition("run.selected", ("r",), "Run", "Benchmark", scope="benchmark", order=140),
        ShortcutDefinition("run.all", ("a",), "Run all", "Benchmark", scope="benchmark", order=150),
        ShortcutDefinition("results", ("v",), "Results", "Benchmark", scope="benchmark", order=160),
        ShortcutDefinition("cancel", ("c",), "Cancel", "Benchmark", scope="benchmark", order=170),
        ShortcutDefinition("errors", ("e",), "Errors", "Benchmark", scope="benchmark", order=180),
        ShortcutDefinition("refresh", ("x",), "Refresh", "Benchmark", scope="benchmark", order=190),
    ]
)
