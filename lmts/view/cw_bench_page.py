from __future__ import annotations

from pathlib import Path

from lmts.core.cw_bench import DEFAULT_CIC_ROOT, DEFAULT_CW_SOURCES_ROOT, CICAdapter, CWSource, discover_cw_sources
from lmts.view.cw_bench import start_cw_bench


class CWBenchPage:
    def __init__(
        self,
        controller,
        *,
        sources_root: Path = DEFAULT_CW_SOURCES_ROOT,
        cic_root: Path = DEFAULT_CIC_ROOT,
    ) -> None:
        self.controller = controller
        self.sources_root = sources_root
        self.cic_root = cic_root
        self.source: CWSource | None = None
        self.output_language: str | None = None
        self.target_ids: set[str] = set()
        self._cic_identity = None

    def _sources(self) -> tuple[CWSource, ...]:
        return discover_cw_sources(self.sources_root)

    def _identity(self):
        if self._cic_identity is None:
            self._cic_identity = CICAdapter(self.cic_root).identity()
        return self._cic_identity

    def refresh_cic(self) -> None:
        self._cic_identity = CICAdapter(self.cic_root).identity()
        if self.output_language not in self._cic_identity.output_languages:
            self.output_language = None

    def lines(self) -> tuple[str, ...]:
        models = [target for target in self.controller.state.targets if target.kind == "model"]
        selected = [target.id for target in models if target.id in self.target_ids]
        try:
            sources = self._sources()
            source_status = f"{len(sources)} source(s)"
        except ValueError as exc:
            source_status = f"ERROR: {exc}"
        try:
            identity = self._identity()
            cic_line = f"{identity.importer_ref} {identity.version} [{identity.source_digest[:12]}]"
            languages = ", ".join(identity.output_languages) if identity.output_languages else "<none>"
        except ValueError as exc:
            cic_line = f"ERROR: {exc}"
            languages = "<unavailable>"
        return (
            "Challenge / CW Bench",
            "",
            f"CW sources      : {self.sources_root} ({source_status})",
            f"Selected source : {self.source.ref if self.source is not None else '-'}",
            f"Source digest   : {self.source.digest[:16] if self.source is not None else '-'}",
            f"Output language : {self.output_language or '-'}",
            f"Models          : {len(selected)} selected / {len(models)} available",
            f"CIC             : {cic_line}",
            f"CIC languages   : {languages}",
            "",
            "The selected implementation is generated through LMTS Workspace Protocol,",
            "imported back to CW through CIC, then compared inside the canonical CW frame.",
            "",
            *(f"  {target_id}" for target_id in selected),
        )

    def choose_source(self, host, stdscr) -> None:
        try:
            sources = self._sources()
        except ValueError as exc:
            host.message = f"CW source discovery failed: {exc}"
            return
        if not sources:
            host.message = f"no CW sources found in {self.sources_root}"
            return
        current = 0
        if self.source is not None:
            for index, item in enumerate(sources):
                if item.ref == self.source.ref and item.digest == self.source.digest:
                    current = index
                    break
        chosen = host.choose(
            stdscr,
            "CW source",
            [f"{source.ref}  {source.name}  [{source.digest[:12]}]" for source in sources],
            current,
        )
        if chosen is not None:
            self.source = sources[chosen]
            host.message = f"CW source: {self.source.ref}"

    def choose_language(self, host, stdscr) -> None:
        try:
            identity = self._identity()
        except ValueError as exc:
            host.message = f"CIC unavailable: {exc}"
            return
        languages = list(identity.output_languages)
        if not languages:
            host.message = "CIC reports no available output-language parsers"
            return
        current = languages.index(self.output_language) if self.output_language in languages else 0
        chosen = host.choose(stdscr, "CW Bench output language", languages, current)
        if chosen is not None:
            self.output_language = languages[chosen]
            host.message = f"CW output language: {self.output_language}"

    def choose_models(self, host, stdscr) -> None:
        models = [target for target in self.controller.state.targets if target.kind == "model"]
        if not models:
            host.message = "no model targets discovered"
            return
        selected = {index for index, target in enumerate(models) if target.id in self.target_ids}
        chosen = host.choose_many(
            stdscr,
            "CW Bench models",
            [target.id for target in models],
            selected,
            include_all=True,
            all_label="All models",
        )
        if chosen is not None:
            self.target_ids = {models[index].id for index in chosen if 0 <= index < len(models)}
            host.message = f"CW Bench: {len(self.target_ids)} model(s) selected"

    def run(self, host) -> bool:
        if self.source is None:
            host.message = "select a CW source"
            return False
        if self.output_language is None:
            host.message = "select an output language"
            return False
        if not self.target_ids:
            host.message = "select at least one model"
            return False
        try:
            self.refresh_cic()
        except ValueError as exc:
            host.message = f"CIC unavailable: {exc}"
            return False
        if self.output_language is None:
            host.message = "selected output language is no longer provided by CIC"
            return False
        started = start_cw_bench(
            self.controller,
            source=self.source,
            output_language=self.output_language,
            target_ids=set(self.target_ids),
            cic_root=self.cic_root,
        )
        host.message = self.controller.state.message
        return started
