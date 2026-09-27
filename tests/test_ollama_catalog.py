from __future__ import annotations

from lmts.tools.ollama_catalog import OllamaCatalogScraper


def test_ollama_catalog_scrapes_library_families_without_api_fallback() -> None:
    scraper = OllamaCatalogScraper()
    scraper._fetch = lambda url: """
    <html><body>
      <a href="/library/qwen3">qwen3</a>
      <a href="/library/llama3.2">llama3.2</a>
      <a href="/library/qwen3:4b">not a family</a>
    </body></html>
    """

    assert scraper.list_families() == ('llama3.2', 'qwen3')


def test_ollama_catalog_scrapes_tag_metadata_from_html_cards() -> None:
    scraper = OllamaCatalogScraper()
    scraper._fetch = lambda url: """
    <html><body>
      <a href="/library/qwen3:4b-q4_K_M">
        qwen3:4b-q4_K_M 2bfd38a7daaf 2.6GB 40K context window Text input
      </a>
      <a href="/library/qwen3:32b-q8_0">
        qwen3:32b-q8_0 a46beca077e5 35GB 40K context window Text input
      </a>
    </body></html>
    """

    candidates = scraper.list_tags('qwen3')

    assert len(candidates) == 2
    first = candidates[0]
    assert first.model_ref == 'qwen3:32b-q8_0'
    assert first.size_bytes == 35 * 1000 ** 3
    assert first.parameter_size == '32B'
    assert first.quantization == 'q8_0'
    assert first.context_length == 40 * 1024
    assert first.digest == 'a46beca077e5'
