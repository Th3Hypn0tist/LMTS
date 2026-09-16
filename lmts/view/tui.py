from __future__ import annotations

from .tui_app import TUIApplication


def run() -> None:
    TUIApplication().run()


def main() -> int:
    run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
