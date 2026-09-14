from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lmts.core.cw_bench import CICAdapter, CWSource, compare_cw
from lmts.core.scoring import ScoreDimension, TestScore
from lmts.lib.workspace import WorkspaceProtocolSession
from lmts.tests.base import TestContext, TestRequirements, TestResult


LANGUAGE_EXTENSION = {
    "python": ".py",
    "javascript": ".js",
    "html": ".html",
    "css": ".css",
}


def _expected_output_paths(source: CWSource, language: str) -> tuple[str, ...]:
    extension = LANGUAGE_EXTENSION.get(language)
    if extension is None:
        raise ValueError(f"CW Bench output language is not supported by this test module: {language}")
    paths: list[str] = []
    for entity in source.document.get("entities", []):
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if not isinstance(entity_id, str) or not entity_id.startswith("#FILE:"):
            continue
        raw = entity_id[len("#FILE:"):]
        parts = raw.split(":") if raw else []
        if not parts:
            continue
        name = parts[-1]
        suffix = PurePosixPath(name).suffix
        stem = name[:-len(suffix)] if suffix else name
        if not stem:
            raise ValueError(f"CW source file identity cannot map to output language: {entity_id}")
        paths.append(str(PurePosixPath(*parts[:-1], stem + extension)))
    if not paths:
        raise ValueError(f"CW source has no #FILE entities: {source.ref}")
    if len(paths) != len(set(paths)):
        raise ValueError(f"CW source collapses to duplicate {language} output paths")
    return tuple(sorted(paths))


@dataclass(frozen=True, slots=True)
class CWDeepTest:
    source: CWSource
    output_language: str
    cic_root: Path
    max_workspace_steps: int = 128
    id: str = "deep.cw_bench"
    version: str = "1.0.0"
    minimum_level: str = "deep"
    mandatory: bool = False
    requirements: TestRequirements = TestRequirements(
        text_generation=True,
        workspace_read=True,
        workspace_write=True,
        multi_file_output=True,
    )

    def run(self, context: TestContext) -> TestResult:
        adapter = CICAdapter(self.cic_root)
        cic_identity = adapter.identity()
        if self.output_language not in cic_identity.output_languages:
            raise ValueError(
                f"CIC {cic_identity.version} does not provide a parser for output language {self.output_language!r}; "
                f"available: {', '.join(cic_identity.output_languages)}"
            )

        expected_paths = _expected_output_paths(self.source, self.output_language)
        context.workspace.stage_input(
            "source.cw.json",
            self.source.path.read_text(encoding="utf-8"),
        )
        context.workspace.stage_input(
            "task.txt",
            "Implement the supplied Canonical Wireframe as source code.\n"
            f"Output language: {self.output_language}.\n"
            "The implementation will be imported back into Canonical Wireframe with CIC and compared to the source CW.\n"
            "Preserve canonical file identity, functions, dependencies, events, effects and explicit semantics.\n"
            "Do not invent fallback behavior or duplicate canonical truth.\n"
            "Write only implementation files to the output mount.\n"
            f"Required output paths: {', '.join(expected_paths)}\n"
            "Read input/source.cw.json before writing implementation files.\n",
        )

        session = WorkspaceProtocolSession(max_steps=self.max_workspace_steps)
        protocol = session.run(
            context,
            "Read input/task.txt and input/source.cw.json, implement the CW exactly in the requested output language, then finish.",
        )
        if not protocol.finished:
            raise ValueError("CW Bench workspace protocol did not finish")

        output_files = tuple(
            str(path.relative_to(context.workspace.output_root).as_posix())
            for path in sorted(context.workspace.output_root.rglob("*"))
            if path.is_file()
        )
        if output_files != expected_paths:
            raise ValueError(
                f"CW Bench output file set mismatch; expected {list(expected_paths)}, got {list(output_files)}"
            )

        imported_root = context.workspace.root / "cw-import"
        imported = adapter.import_code(context.workspace.output_root, imported_root)
        unexpected_languages = sorted(set(imported.observed_languages) - {self.output_language})
        if unexpected_languages:
            raise ValueError(
                f"CIC observed unexpected output language(s): {', '.join(unexpected_languages)}"
            )

        comparison = compare_cw(self.source.document, imported.document)
        dimensions = tuple(
            ScoreDimension(
                id=dimension_id,
                score=score,
                evidence=comparison.evidence.get(dimension_id, {}),
            )
            for dimension_id, score in sorted(comparison.dimensions.items())
        )
        score = TestScore(dimensions)
        passed = comparison.exact and imported.report.get("verdict") == "PASS"

        return TestResult(
            passed=passed,
            score=score,
            metrics={
                "cw_conformance_percent": comparison.percent,
                "workspace_protocol_steps": protocol.steps,
                "output_file_count": len(output_files),
                "cic_files_seen": imported.import_summary.get("files_seen"),
                "cic_files_imported": imported.import_summary.get("files_imported"),
                "cic_diagnostics": imported.import_summary.get("diagnostics"),
                "cic_report_verdict": imported.report.get("verdict"),
            },
            artifacts={
                "cw_source_ref": self.source.ref,
                "cw_source_digest": self.source.digest,
                "cw_source_path": str(self.source.path),
                "cw_specification_ref": self.source.specification_ref,
                "output_language": self.output_language,
                "output_files": list(output_files),
                "cic": imported.identity.to_dict(),
                "cic_import_summary": imported.import_summary,
                "cic_report": imported.report,
                "cic_observed_languages": list(imported.observed_languages),
                "imported_cw_digest": imported.document_digest,
                "cw_comparison": {
                    "percent": comparison.percent,
                    "exact": comparison.exact,
                    "dimensions": comparison.dimensions,
                    "evidence": comparison.evidence,
                },
                "protocol_summary": protocol.summary,
            },
        )
