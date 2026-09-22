from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from lmts.core.benchmark_runner import BenchmarkRunner
from lmts.core.benchmark_store import BenchmarkStore
from lmts.core.executor import ModelExecutor, TestExecutor
from lmts.core.registry import ProviderRegistry
from lmts.core.runner import TestRunner
from lmts.core.runtime_targets import executor_from_definition, load_runtime_targets
from lmts.core.store import RunStore
from lmts.providers.ollama import OllamaProvider
from lmts.services.auth import AuthService, AuthenticationError
from lmts.services.settings import SettingsService
from lmts.tests.catalog import default_test_matrix, default_test_type_registry
from lmts.tests.modules import TextGenerationTest, WorkspaceMultiFileTest
from lmts.tests.registry import TestRegistry
from lmts.tools.profile import profile_json


def default_provider_registry() -> ProviderRegistry:
    return ProviderRegistry([OllamaProvider()])


def default_test_registry() -> TestRegistry:
    """Compatibility registry for direct one-test CLI execution."""
    return TestRegistry([TextGenerationTest(), WorkspaceMultiFileTest()])


def _models() -> int:
    registry = default_provider_registry()
    try:
        models = registry.discover_models()
    except Exception as exc:
        print(f"model discovery failed: {exc}")
        return 2
    print(json.dumps([
        {
            "id": model.id,
            "provider_ref": model.provider_ref,
            "model_ref": model.model_ref,
            "location": model.location,
            "metadata": model.metadata,
        }
        for model in models
    ], indent=2, ensure_ascii=False))
    return 0


def _discover_targets(providers: ProviderRegistry) -> list[TestExecutor]:
    targets: list[TestExecutor] = [
        ModelExecutor(providers.provider(model.provider_ref), model)
        for model in providers.discover_models()
    ]
    targets.extend(executor_from_definition(item) for item in load_runtime_targets())
    ids = [target.id for target in targets]
    if len(ids) != len(set(ids)):
        raise ValueError("evaluation target ids must be unique across models, bots and compositions")
    return sorted(targets, key=lambda item: (item.kind, item.id.casefold()))


def _targets() -> int:
    providers = default_provider_registry()
    try:
        targets = _discover_targets(providers)
    except Exception as exc:
        print(f"target discovery failed: {exc}")
        return 2
    print(json.dumps([
        {
            "id": target.id,
            "kind": target.kind,
            "subject": target.subject.to_dict(),
            "capabilities": {
                "text": target.capabilities.text,
                "vision": target.capabilities.vision,
                "tools": target.capabilities.tools,
                "structured_output": target.capabilities.structured_output,
                "workspace_read": target.capabilities.workspace_read,
                "workspace_write": target.capabilities.workspace_write,
                "multi_file_output": target.capabilities.multi_file_output,
            },
            "metadata": target.metadata,
        }
        for target in targets
    ], indent=2, ensure_ascii=False))
    return 0


def _tests() -> int:
    registry = default_test_type_registry()
    print(json.dumps([
        {
            "ref": definition.ref,
            "id": definition.id,
            "version": definition.version,
            "title": definition.title,
            "description": definition.description,
            "requirements": {
                "text_generation": definition.requirements.text_generation,
                "vision": definition.requirements.vision,
                "tools": definition.requirements.tools,
                "structured_output": definition.requirements.structured_output,
                "workspace_read": definition.requirements.workspace_read,
                "workspace_write": definition.requirements.workspace_write,
                "multi_file_output": definition.requirements.multi_file_output,
            },
            "parameters": [
                {
                    "name": parameter.name,
                    "label": parameter.label,
                    "kind": parameter.kind,
                    "required": parameter.required,
                    "default": parameter.default,
                    "multiline": parameter.multiline,
                    "minimum": parameter.minimum,
                    "maximum": parameter.maximum,
                    "choices": list(parameter.choices),
                }
                for parameter in definition.parameters
            ],
        }
        for definition in registry.definitions()
    ], indent=2, ensure_ascii=False))
    return 0


def _matrix() -> int:
    registry = default_test_type_registry()
    matrix = default_test_matrix(registry)
    print(json.dumps([
        {
            "ref": test.ref,
            "instance_id": test.instance_id,
            "type_ref": test.type_ref,
            "title": test.title,
            "params": test.params,
        }
        for test in matrix.tests()
    ], indent=2, ensure_ascii=False))
    return 0


def _select_models(providers: ProviderRegistry, model_ids: list[str]) -> list:
    models = providers.discover_models()
    if not model_ids:
        return [model for model in models if model.location == "local"]
    by_id = {model.id: model for model in models}
    missing = [model_id for model_id in model_ids if model_id not in by_id]
    if missing:
        raise KeyError(f"unknown model(s): {', '.join(missing)}")
    return [by_id[model_id] for model_id in model_ids]


def _select_targets(providers: ProviderRegistry, target_ids: list[str]) -> list[TestExecutor]:
    targets = _discover_targets(providers)
    if not target_ids:
        return targets
    by_id = {target.id: target for target in targets}
    missing = [target_id for target_id in target_ids if target_id not in by_id]
    if missing:
        raise KeyError(f"unknown target(s): {', '.join(missing)}")
    return [by_id[target_id] for target_id in target_ids]


def _run(test_ref: str, model_id: str, results: Path, workspaces: Path) -> int:
    providers = default_provider_registry()
    tests = default_test_registry()
    try:
        test = tests.get(test_ref)
        models = _select_models(providers, [model_id])
    except Exception as exc:
        print(f"run setup failed: {exc}")
        return 2
    runner = TestRunner(providers, RunStore(results))
    run, path = runner.run(test, models[0], workspaces)
    print(json.dumps({
        "run_id": run.run_id,
        "test_ref": run.test_ref,
        "executor_id": run.executor_id,
        "executor_kind": run.executor_kind,
        "status": run.status,
        "passed": run.passed,
        "result_path": str(path),
    }, indent=2, ensure_ascii=False))
    return 0 if run.status == "completed" and run.passed is not False else 1


def _benchmark(test_ref: str, target_ids: list[str], results: Path, workspaces: Path) -> int:
    providers = default_provider_registry()
    tests = default_test_registry()
    try:
        test = tests.get(test_ref)
        targets = _select_targets(providers, target_ids)
    except Exception as exc:
        print(f"benchmark setup failed: {exc}")
        return 2
    if not targets:
        print("benchmark setup failed: no matching targets")
        return 2
    run_store = RunStore(results)
    batch = BenchmarkRunner(TestRunner(providers, run_store)).run(test, targets, workspaces)
    batch_path = BenchmarkStore(results).append(batch)
    print(json.dumps({**batch.to_dict(), "batch_path": str(batch_path)}, indent=2, ensure_ascii=False))
    return 0 if batch.failed == 0 and batch.errors == 0 else 1



def _mysql_connection(connection_id: str | None = None):
    settings = SettingsService().load_core()
    if connection_id is None:
        return settings.mysql
    mysql = next((item for item in settings.mysql_connections if item.id == connection_id), None)
    if mysql is None:
        raise ValueError(f'unknown MySQL connection: {connection_id}')
    return mysql


def _auth_service() -> AuthService:
    return AuthService()


def _new_password() -> str:
    first = getpass.getpass('Password: ')
    second = getpass.getpass('Confirm password: ')
    if first != second:
        raise ValueError('passwords do not match')
    return first


def _print_identity(identity) -> None:
    print(json.dumps({
        'user_id': identity.user_id,
        'username': identity.username,
        'tier': identity.tier,
        'verified': identity.verified,
    }, indent=2, ensure_ascii=False))


def _user_login(username: str) -> int:
    try:
        _print_identity(_auth_service().login(username, getpass.getpass('Password: ')))
        return 0
    except (AuthenticationError, RuntimeError, ValueError) as exc:
        print(f'login failed: {exc}')
        return 2


def _user_register(token: str, username: str, email: str | None) -> int:
    try:
        _print_identity(_auth_service().register(token, username, _new_password(), email=email))
        return 0
    except (AuthenticationError, RuntimeError, ValueError) as exc:
        print(f'registration failed: {exc}')
        return 2


def _user_whoami() -> int:
    try:
        identity = _auth_service().current_identity()
        if identity is None:
            print('not authenticated')
            return 1
        _print_identity(identity)
        return 0
    except (AuthenticationError, RuntimeError, ValueError) as exc:
        print(f'whoami failed: {exc}')
        return 2


def _user_logout() -> int:
    try:
        _auth_service().logout()
        print('logged out')
        return 0
    except (AuthenticationError, RuntimeError, ValueError) as exc:
        print(f'logout failed: {exc}')
        return 2


def _reports_rebuild_projections(connection_id: str | None) -> int:
    from lmts.tools.report_projection import rebuild_all_report_projections

    try:
        count = rebuild_all_report_projections(_mysql_connection(connection_id))
    except (RuntimeError, ValueError) as exc:
        print(f'report projection rebuild failed: {exc}')
        return 2
    print(f'rebuilt projections for {count} report(s)')
    return 0


def _tui() -> int:
    from lmts.view.report_export_runtime import run_tui

    run_tui()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="lmts")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("tui", help="Open the interactive LMTS View")
    sub.add_parser("models", help="Discover local models")
    sub.add_parser("targets", help="Discover evaluation targets: models, bots and compositions")
    sub.add_parser("tests", help="List registered test types")
    sub.add_parser("matrix", help="List default configured test matrix")

    user = sub.add_parser("user", help="IAM user authentication")
    user_sub = user.add_subparsers(dest="user_command", required=True)

    user_login = user_sub.add_parser("login", help="Authenticate against IAM")
    user_login.add_argument("username")

    user_register = user_sub.add_parser("register", help="Register through IAM with an invite code")
    user_register.add_argument("token")
    user_register.add_argument("username")
    user_register.add_argument("--email")

    user_sub.add_parser("whoami", help="Show the authenticated IAM identity")
    user_sub.add_parser("logout", help="Revoke the current IAM session")

    reports = sub.add_parser("reports", help="Report storage and projection tools")
    reports_sub = reports.add_subparsers(dest="reports_command", required=True)
    reports_rebuild = reports_sub.add_parser("rebuild-projections", help="Rebuild derived SQL indexes from immutable report_json")
    reports_rebuild.add_argument("--connection")

    profile = sub.add_parser("profile", help="System profile tools")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_sub.add_parser("scan", help="Scan current system")

    run = sub.add_parser("run", help="Run one compatibility test module against one model")
    run.add_argument("test_ref", help="Versioned test ref, for example core.text_generation@1.0.0")
    run.add_argument("model_id", help="Discovered model id, for example ollama-local:qwen3:4b")
    run.add_argument("--results", type=Path, default=Path("results"))
    run.add_argument("--workspaces", type=Path, default=Path(".lmts/workspaces"))

    benchmark = sub.add_parser("benchmark", help="Run one compatibility test module against evaluation targets")
    benchmark.add_argument("test_ref", help="Versioned test ref")
    benchmark.add_argument("target_ids", nargs="*", help="Target ids; omit to run all discovered targets")
    benchmark.add_argument("--results", type=Path, default=Path("results"))
    benchmark.add_argument("--workspaces", type=Path, default=Path(".lmts/workspaces"))

    args = parser.parse_args()
    if args.command in {None, "tui"}:
        return _tui()
    if args.command == "models":
        return _models()
    if args.command == "targets":
        return _targets()
    if args.command == "tests":
        return _tests()
    if args.command == "matrix":
        return _matrix()
    if args.command == "profile" and args.profile_command == "scan":
        print(profile_json())
        return 0
    if args.command == "reports" and args.reports_command == "rebuild-projections":
        return _reports_rebuild_projections(args.connection)

    if args.command == "user" and args.user_command == "login":
        return _user_login(args.username)
    if args.command == "user" and args.user_command == "register":
        return _user_register(args.token, args.username, args.email)
    if args.command == "user" and args.user_command == "whoami":
        return _user_whoami()
    if args.command == "user" and args.user_command == "logout":
        return _user_logout()
    if args.command == "run":
        return _run(args.test_ref, args.model_id, args.results, args.workspaces)
    if args.command == "benchmark":
        return _benchmark(args.test_ref, args.target_ids, args.results, args.workspaces)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
