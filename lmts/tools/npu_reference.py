from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

NPU_REFERENCE_CONFIG_SCHEMA_VERSION = 1
DEFAULT_NPU_REFERENCE_CONFIG_PATH = Path('.lmts/npu-reference.json')


class NPUUnavailable(RuntimeError):
    pass


class NPUReferenceAdapter(Protocol):
    id: str

    def available(self) -> bool: ...

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class CommandNPUReferenceAdapter:
    id: str
    command: tuple[str, ...]
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError('NPU adapter id must not be empty')
        if not self.command:
            raise ValueError('NPU command adapter requires a command')
        if self.timeout_seconds <= 0:
            raise ValueError('NPU command adapter timeout must be positive')

    def available(self) -> bool:
        executable = self.command[0]
        if '/' in executable or '\\' in executable:
            return Path(executable).expanduser().is_file()
        return shutil.which(executable) is not None

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not self.available():
            raise NPUUnavailable(f'NPU backend executable is unavailable: {self.command[0]}')
        request = json.dumps({'protocol': 'lmts.npu.reference.v1'}) + '\n'
        try:
            completed = subprocess.run(
                list(self.command),
                input=request,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise NPUUnavailable(f'NPU backend execution failed: {exc}') from exc
        if completed.returncode != 0:
            raise NPUUnavailable(
                f'NPU backend exited with code {completed.returncode}: {completed.stderr.strip()}'
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise NPUUnavailable(f'NPU backend returned invalid JSON: {exc}') from exc
        if not isinstance(payload, dict):
            raise NPUUnavailable('NPU backend response must be a JSON object')
        if payload.get('protocol') not in {None, 'lmts.npu.reference.v1'}:
            raise NPUUnavailable('NPU backend returned an unsupported protocol version')
        tests = payload.get('tests')
        if not isinstance(tests, list) or not tests:
            raise NPUUnavailable('NPU backend returned no benchmark tests')
        if not all(isinstance(test, dict) for test in tests):
            raise NPUUnavailable('NPU backend tests must be JSON objects')
        environment = payload.get('environment') if isinstance(payload.get('environment'), dict) else {}
        return [dict(test) for test in tests], {
            'backend': self.id,
            'transport': 'subprocess',
            **environment,
        }


@dataclass(slots=True)
class NPUReferenceRegistry:
    adapters: tuple[NPUReferenceAdapter, ...] = ()

    def available_adapters(self) -> tuple[NPUReferenceAdapter, ...]:
        return tuple(adapter for adapter in self.adapters if adapter.available())

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        available = self.available_adapters()
        if not available:
            raise NPUUnavailable('no configured NPU reference backend is available')
        tests: list[dict[str, Any]] = []
        backends: list[str] = []
        environments: dict[str, Any] = {}
        for adapter in available:
            adapter_tests, environment = adapter.benchmark()
            tests.extend(adapter_tests)
            backends.append(adapter.id)
            environments[adapter.id] = environment
        return tests, {'backends': backends, 'backend_environments': environments}


def load_npu_reference_registry(path: Path = DEFAULT_NPU_REFERENCE_CONFIG_PATH) -> NPUReferenceRegistry:
    path = path.expanduser()
    if not path.is_file():
        return NPUReferenceRegistry()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid NPU reference config: {exc}') from exc
    if not isinstance(payload, dict) or payload.get('schema_version') != NPU_REFERENCE_CONFIG_SCHEMA_VERSION:
        raise ValueError('unsupported NPU reference config schema')
    raw_backends = payload.get('backends')
    if not isinstance(raw_backends, list):
        raise ValueError('NPU reference config backends must be a list')
    adapters: list[CommandNPUReferenceAdapter] = []
    for raw in raw_backends:
        if not isinstance(raw, dict):
            raise ValueError('NPU reference backend must be an object')
        command_raw = raw.get('command')
        if isinstance(command_raw, str):
            command = tuple(shlex.split(command_raw))
        elif isinstance(command_raw, list):
            command = tuple(str(item) for item in command_raw)
        else:
            command = ()
        adapters.append(
            CommandNPUReferenceAdapter(
                id=str(raw.get('id') or '').strip(),
                command=command,
                timeout_seconds=float(raw.get('timeout_seconds') or 120.0),
            )
        )
    ids = [adapter.id for adapter in adapters]
    if len(ids) != len(set(ids)):
        raise ValueError('NPU reference backend ids must be unique')
    return NPUReferenceRegistry(tuple(adapters))


class _ConfiguredNPUReferenceRegistry:
    """Canonical default: only explicitly configured command backends are used."""

    def available_adapters(self) -> tuple[NPUReferenceAdapter, ...]:
        return load_npu_reference_registry().available_adapters()

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return load_npu_reference_registry().benchmark()


DEFAULT_NPU_REFERENCE_REGISTRY = _ConfiguredNPUReferenceRegistry()


def benchmark_configured_npu_reference(
    path: Path = DEFAULT_NPU_REFERENCE_CONFIG_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return load_npu_reference_registry(path).benchmark()
