from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_CW_SOURCES_ROOT = Path("CW_sources")
DEFAULT_CIC_ROOT = Path("../Structure")
CIC_IMPORTER_REF = "Structure/CIC"


def _canonical_json_digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CWSource:
    ref: str
    identity_id: str
    version: str
    name: str
    specification_ref: str | None
    path: Path
    digest: str
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CICIdentity:
    importer_ref: str
    root: Path
    source_commit: str
    source_digest: str
    ir_version: str
    output_languages: tuple[str, ...]

    @property
    def version(self) -> str:
        return f"{self.ir_version}@{self.source_commit}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "importer_ref": self.importer_ref,
            "root": str(self.root),
            "version": self.version,
            "source_commit": self.source_commit,
            "source_digest": self.source_digest,
            "ir_version": self.ir_version,
            "output_languages": list(self.output_languages),
        }


@dataclass(frozen=True, slots=True)
class CICImportResult:
    identity: CICIdentity
    import_summary: dict[str, Any]
    ir: dict[str, Any]
    document: dict[str, Any]
    report: dict[str, Any]
    document_digest: str
    observed_languages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CWComparison:
    dimensions: dict[str, float]
    evidence: dict[str, Any]

    @property
    def percent(self) -> float:
        if not self.dimensions:
            return 0.0
        return sum(self.dimensions.values()) / len(self.dimensions)

    @property
    def exact(self) -> bool:
        return bool(self.dimensions) and all(value == 100.0 for value in self.dimensions.values())


def load_cw_source(path: Path) -> CWSource:
    candidate = path.expanduser().resolve()
    if not candidate.is_file() or candidate.suffix.lower() != ".json":
        raise ValueError(f"CW source must be a JSON file: {candidate}")
    try:
        document = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read CW source {candidate}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"CW source root must be an object: {candidate}")
    identity = document.get("identity")
    if not isinstance(identity, dict):
        raise ValueError(f"CW source identity missing: {candidate}")
    identity_id = identity.get("id")
    version = identity.get("version")
    if not isinstance(identity_id, str) or not identity_id.strip():
        raise ValueError(f"CW source identity.id missing: {candidate}")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"CW source identity.version missing: {candidate}")
    entities = document.get("entities")
    if not isinstance(entities, list):
        raise ValueError(f"CW source entities must be an array: {candidate}")
    name = identity.get("name")
    specification_ref = document.get("specification_ref")
    return CWSource(
        ref=f"{identity_id.strip()}@{version.strip()}",
        identity_id=identity_id.strip(),
        version=version.strip(),
        name=str(name).strip() if isinstance(name, str) and name.strip() else identity_id.strip(),
        specification_ref=specification_ref if isinstance(specification_ref, str) else None,
        path=candidate,
        digest=_canonical_json_digest(document),
        document=document,
    )


def discover_cw_sources(root: Path = DEFAULT_CW_SOURCES_ROOT) -> tuple[CWSource, ...]:
    directory = root.expanduser().resolve()
    if not directory.exists():
        return ()
    if not directory.is_dir():
        raise ValueError(f"CW source root is not a directory: {directory}")
    sources = [load_cw_source(path) for path in sorted(directory.rglob("*.json"), key=lambda item: item.as_posix().casefold())]
    refs = [source.ref for source in sources]
    duplicates = sorted(ref for ref, count in Counter(refs).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate CW source ref(s): {', '.join(duplicates)}")
    return tuple(sources)


class CICAdapter:
    def __init__(self, root: Path = DEFAULT_CIC_ROOT, *, timeout_seconds: float = 120.0) -> None:
        self.root = root.expanduser().resolve()
        self.timeout_seconds = timeout_seconds

    def _require_root(self) -> None:
        if not (self.root / "CIC" / "api.py").is_file():
            raise ValueError(f"CIC implementation not found: {self.root / 'CIC'}")

    def _run(self, args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        self._require_root()
        result = subprocess.run(
            args,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds if timeout is None else timeout,
            check=False,
        )
        return result

    def _git_commit(self) -> str:
        result = self._run(["git", "rev-parse", "HEAD"], timeout=15.0)
        commit = result.stdout.strip()
        if result.returncode != 0 or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit.lower()):
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise ValueError(f"cannot identify CIC git commit: {detail}")
        return commit.lower()

    def _source_digest(self) -> str:
        digest = hashlib.sha256()
        files = [
            path
            for path in sorted((self.root / "CIC").rglob("*"), key=lambda item: item.as_posix().casefold())
            if path.is_file() and path.suffix.lower() in {".py", ".json"} and "__pycache__" not in path.parts
        ]
        if not files:
            raise ValueError(f"CIC source files not found: {self.root / 'CIC'}")
        for path in files:
            relative = path.relative_to(self.root).as_posix().encode("utf-8")
            raw = path.read_bytes()
            digest.update(relative)
            digest.update(b"\0")
            digest.update(str(len(raw)).encode("ascii"))
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
        return digest.hexdigest()

    def identity(self) -> CICIdentity:
        script = (
            "import json; "
            "from CIC.api_legacy import import_files; "
            "bundle=import_files([]); "
            "print(json.dumps({'ir_version': bundle.ir.get('version'), "
            "'languages': bundle.ir.get('policy', {}).get('builtin_frontends', [])}))"
        )
        result = self._run([sys.executable, "-c", script], timeout=30.0)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise ValueError(f"CIC capability probe failed: {detail}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CIC capability probe returned invalid JSON: {exc}") from exc
        ir_version = payload.get("ir_version") if isinstance(payload, dict) else None
        languages = payload.get("languages") if isinstance(payload, dict) else None
        if not isinstance(ir_version, str) or not ir_version:
            raise ValueError("CIC capability probe did not return ir_version")
        if not isinstance(languages, list) or not all(isinstance(value, str) and value for value in languages):
            raise ValueError("CIC capability probe did not return output languages")
        return CICIdentity(
            importer_ref=CIC_IMPORTER_REF,
            root=self.root,
            source_commit=self._git_commit(),
            source_digest=self._source_digest(),
            ir_version=ir_version,
            output_languages=tuple(sorted(set(languages))),
        )

    def import_code(self, code_folder: Path, cw_folder: Path) -> CICImportResult:
        identity = self.identity()
        source = code_folder.expanduser().resolve()
        target = cw_folder.expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"CW Bench code folder not found: {source}")
        if target.exists():
            raise ValueError(f"CW Bench CIC output already exists: {target}")

        imported = self._run([sys.executable, "-m", "CIC", "import", str(source), str(target)])
        if imported.returncode != 0:
            detail = imported.stderr.strip() or imported.stdout.strip() or f"exit {imported.returncode}"
            raise ValueError(f"CIC import failed: {detail}")
        try:
            import_summary = json.loads(imported.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CIC import returned invalid JSON: {exc}") from exc

        ir_path = target / "import.ir.json"
        try:
            ir = json.loads(ir_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"CIC import IR unavailable: {exc}") from exc
        actual_ir_version = ir.get("version") if isinstance(ir, dict) else None
        if actual_ir_version != identity.ir_version:
            raise ValueError(f"CIC IR version changed during run: {identity.ir_version!r} -> {actual_ir_version!r}")

        document_script = (
            "import json,sys; from CIC import ingest_cw; "
            "print(json.dumps(ingest_cw(sys.argv[1]), ensure_ascii=False))"
        )
        assembled = self._run([sys.executable, "-c", document_script, str(target)])
        if assembled.returncode != 0:
            detail = assembled.stderr.strip() or assembled.stdout.strip() or f"exit {assembled.returncode}"
            raise ValueError(f"CIC CW assembly failed: {detail}")
        try:
            document = json.loads(assembled.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CIC CW assembly returned invalid JSON: {exc}") from exc

        reported = self._run([sys.executable, "-m", "CIC", "report", str(target), "--json"])
        try:
            report = json.loads(reported.stdout)
        except json.JSONDecodeError as exc:
            detail = reported.stderr.strip() or reported.stdout.strip() or f"exit {reported.returncode}"
            raise ValueError(f"CIC report returned invalid JSON: {detail}") from exc

        observed_languages = sorted({
            str(file_record.get("language_ir", {}).get("language_id"))
            for file_record in ir.get("files", [])
            if isinstance(file_record, dict)
            and isinstance(file_record.get("language_ir"), dict)
            and isinstance(file_record.get("language_ir", {}).get("language_id"), str)
        })
        return CICImportResult(
            identity=identity,
            import_summary=import_summary if isinstance(import_summary, dict) else {},
            ir=ir if isinstance(ir, dict) else {},
            document=document if isinstance(document, dict) else {},
            report=report if isinstance(report, dict) else {},
            document_digest=_canonical_json_digest(document),
            observed_languages=tuple(observed_languages),
        )


def _canonical_file_key_from_ref(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("#FILE:"):
        return None
    raw = value[len("#FILE:"):]
    parts = raw.split(":") if raw else []
    if not parts:
        return None
    final = parts[-1]
    suffix = PurePosixPath(final).suffix
    if suffix:
        final = final[:-len(suffix)]
    if not final:
        return None
    return ":".join([*parts[:-1], final])


def _file_keys(document: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for entity in document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        key = _canonical_file_key_from_ref(entity.get("id"))
        if key:
            result.add(key)
    return result


def _function_keys(document: dict[str, Any]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for entity in document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        file_key = _canonical_file_key_from_ref(entity.get("id"))
        if not file_key:
            continue
        for prop in entity.get("properties", []):
            if not isinstance(prop, dict) or prop.get("property_type_ref") != "function":
                continue
            value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
            details = value.get("properties") if isinstance(value.get("properties"), dict) else {}
            name = details.get("name")
            if not isinstance(name, str) or not name:
                qualified = details.get("qualified_name")
                if isinstance(qualified, str) and qualified:
                    name = qualified.split(".")[-1].split(":")[-1]
            if not isinstance(name, str) or not name:
                function_type = value.get("function_type_ref")
                name = function_type if isinstance(function_type, str) and function_type else None
            if isinstance(name, str) and name:
                result.add((file_key, name))
    return result


def _semantic_values(document: dict[str, Any], property_type: str, value_key: str) -> set[str]:
    result: set[str] = set()
    for entity in document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        for prop in entity.get("properties", []):
            if not isinstance(prop, dict) or prop.get("property_type_ref") != property_type:
                continue
            value = prop.get("value") if isinstance(prop.get("value"), dict) else {}
            semantic = value.get(value_key)
            if isinstance(semantic, str) and semantic:
                result.add(semantic)
    return result


def _link_types(document: dict[str, Any]) -> set[str]:
    return _semantic_values(document, "link", "link_type_ref")


def _coverage(expected: set[Any], actual: set[Any]) -> tuple[float, dict[str, Any]]:
    matched = expected & actual
    if not expected:
        return 100.0, {"expected": [], "actual": sorted(actual), "matched": [], "missing": [], "unexpected": sorted(actual)}
    missing = expected - actual
    unexpected = actual - expected
    return (
        len(matched) / len(expected) * 100.0,
        {
            "expected": sorted(expected),
            "actual": sorted(actual),
            "matched": sorted(matched),
            "missing": sorted(missing),
            "unexpected": sorted(unexpected),
        },
    )


def compare_cw(expected: dict[str, Any], actual: dict[str, Any]) -> CWComparison:
    expected_files = _file_keys(expected)
    actual_files = _file_keys(actual)
    expected_functions = _function_keys(expected)
    actual_functions = _function_keys(actual)
    expected_events = _semantic_values(expected, "event", "event_type_ref")
    actual_events = _semantic_values(actual, "event", "event_type_ref")
    expected_effects = _semantic_values(expected, "effect", "effect_type_ref")
    actual_effects = _semantic_values(actual, "effect", "effect_type_ref")
    expected_links = _link_types(expected)
    actual_links = _link_types(actual)

    dimensions: dict[str, float] = {}
    evidence: dict[str, Any] = {}
    for dimension_id, left, right in (
        ("cw_file_identity", expected_files, actual_files),
        ("cw_functions", expected_functions, actual_functions),
        ("cw_events", expected_events, actual_events),
        ("cw_effects", expected_effects, actual_effects),
        ("cw_link_semantics", expected_links, actual_links),
    ):
        score, detail = _coverage(left, right)
        dimensions[dimension_id] = score
        evidence[dimension_id] = detail
    return CWComparison(dimensions=dimensions, evidence=evidence)
