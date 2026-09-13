from __future__ import annotations

import argparse
import json

from lmts.core.registry import ProviderRegistry
from lmts.providers.ollama import OllamaProvider
from lmts.tools.profile import profile_json


def _models() -> int:
    registry = ProviderRegistry([OllamaProvider()])
    try:
        models = registry.discover_models()
    except Exception as exc:
        print(f"model discovery failed: {exc}")
        return 2
    print(json.dumps([{"id": model.id, "provider_ref": model.provider_ref, "model_ref": model.model_ref, "location": model.location, "metadata": model.metadata} for model in models], indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="lmts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models", help="Discover local models")
    profile = sub.add_parser("profile", help="System profile tools")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_sub.add_parser("scan", help="Scan current system")
    args = parser.parse_args()
    if args.command == "models":
        return _models()
    if args.command == "profile" and args.profile_command == "scan":
        print(profile_json())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
