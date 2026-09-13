from __future__ import annotations

from lmts.cli import default_provider_registry, default_test_registry

from .controller import LMTSViewController
from .projector import LMTSViewProjector


def render() -> str:
    controller = LMTSViewController(default_provider_registry(), default_test_registry())
    controller.refresh()
    return LMTSViewProjector(controller.state).project().text()


def main() -> int:
    print(render(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
