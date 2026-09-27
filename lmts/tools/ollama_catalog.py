from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote
from urllib.request import Request, urlopen

from lmts.core.model_explorer import ModelCandidate


OLLAMA_LIBRARY_URL = 'https://ollama.com/library'


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() != 'a' or self._href is not None:
            return
        href = next((value for key, value in attrs if key == 'href'), None)
        if isinstance(href, str):
            self._href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != 'a' or self._href is None:
            return
        text = ' '.join(' '.join(self._parts).split())
        self.anchors.append((self._href, text))
        self._href = None
        self._parts = []


def _size_bytes(text: str) -> int | None:
    match = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)(?!\w)', text, re.IGNORECASE)
    if match is None:
        return None
    amount = float(match.group(1))
    factors = {'KB': 1000, 'MB': 1000 ** 2, 'GB': 1000 ** 3, 'TB': 1000 ** 4}
    return int(amount * factors[match.group(2).upper()])


def _context_length(text: str) -> int | None:
    match = re.search(r'(\d+(?:\.\d+)?)\s*([KM])?\s+context(?:\s+window)?', text, re.IGNORECASE)
    if match is None:
        return None
    amount = float(match.group(1))
    suffix = (match.group(2) or '').upper()
    factor = 1024 if suffix == 'K' else 1024 ** 2 if suffix == 'M' else 1
    return int(amount * factor)


def _parameter_size(model_ref: str) -> str | None:
    tag = model_ref.partition(':')[2]
    match = re.search(r'(?<![\w.])(\d+(?:\.\d+)?[bm])(?![\w.])', tag, re.IGNORECASE)
    return match.group(1).upper() if match is not None else None


def _quantization(model_ref: str) -> str | None:
    tag = model_ref.partition(':')[2]
    match = re.search(r'(q\d+(?:_[A-Za-z0-9]+)*|fp\d+)', tag, re.IGNORECASE)
    return match.group(1) if match is not None else None


class OllamaCatalogScraper:
    """HTML scraper for Ollama's public model library; no catalogue API fallback."""

    def __init__(self, base_url: str = OLLAMA_LIBRARY_URL, *, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def _fetch(self, url: str) -> str:
        req = Request(
            url,
            headers={
                'Accept': 'text/html',
                'User-Agent': 'LMTS-Model-Explorer/1.0',
            },
            method='GET',
        )
        with urlopen(req, timeout=self.timeout) as response:
            return response.read().decode('utf-8', errors='strict')

    @staticmethod
    def _anchors(html: str) -> list[tuple[str, str]]:
        parser = _AnchorParser()
        parser.feed(html)
        return parser.anchors

    def list_families(self) -> tuple[str, ...]:
        families: set[str] = set()
        for href, _text in self._anchors(self._fetch(self.base_url)):
            match = re.fullmatch(r'/library/([A-Za-z0-9._-]+)', href)
            if match is not None:
                families.add(match.group(1))
        return tuple(sorted(families, key=str.casefold))

    def list_tags(self, family: str) -> tuple[ModelCandidate, ...]:
        family = family.strip()
        if not family or not re.fullmatch(r'[A-Za-z0-9._-]+', family):
            raise ValueError('invalid Ollama library family')
        url = f'{self.base_url}/{quote(family, safe="")}/tags'
        candidates: dict[str, ModelCandidate] = {}
        pattern = re.compile(rf'/library/{re.escape(family)}:([^/?#]+)$', re.IGNORECASE)
        for href, text in self._anchors(self._fetch(url)):
            match = pattern.fullmatch(href)
            if match is None:
                continue
            tag = match.group(1)
            model_ref = f'{family}:{tag}'
            digest_match = re.search(r'\b[0-9a-f]{12}\b', text, re.IGNORECASE)
            candidate = ModelCandidate(
                provider='ollama',
                model_ref=model_ref,
                family=family,
                size_bytes=_size_bytes(text),
                parameter_size=_parameter_size(model_ref),
                quantization=_quantization(model_ref),
                context_length=_context_length(text),
                digest=digest_match.group(0).lower() if digest_match is not None else None,
                source_url=f'{self.base_url}/{quote(model_ref, safe=":")}',
            )
            previous = candidates.get(model_ref)
            if previous is None or (
                previous.size_bytes is None and candidate.size_bytes is not None
            ):
                candidates[model_ref] = candidate
        return tuple(sorted(candidates.values(), key=lambda item: item.model_ref.casefold()))
