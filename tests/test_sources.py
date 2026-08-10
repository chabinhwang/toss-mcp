import unittest

import httpx

from toss_mcp.chunker import MAX_CHUNK_LEN, chunk_all, chunk_document
from toss_mcp.collector import (
    SOURCES,
    _response_validator,
    parse_links,
    source_urls,
    source_validator_key,
)
from toss_mcp.knowledge import STATIC_SOURCES, collect_static_sources
from toss_mcp.searcher import search


class OfficialSourcesTest(unittest.TestCase):
    def test_all_official_document_families_register_index_and_full_roots(self):
        self.assertEqual(
            {
                source_key: {role for role, _ in source_urls(source)}
                for source_key, source in SOURCES.items()
            },
            {
                "apps_in_toss": {"index", "full"},
                "tds_react_native": {"index", "full"},
                "tds_mobile": {"index", "full"},
            },
        )

        for source_key, source in SOURCES.items():
            for role, url in source_urls(source):
                self.assertTrue(url.startswith("https://"))
                self.assertTrue(url.endswith(("/llms.txt", "/llms-full.txt")))
                self.assertEqual(
                    source_validator_key(source_key, role),
                    f"{source_key}:{role}",
                )

    def test_parse_links_supports_relative_urls_and_removes_duplicates(self):
        links = parse_links(
            """- [First](/guide/first.md)
- [Duplicate](/guide/first.md)
- [External](https://example.com/second.md)
- [Anchor](#ignored)""",
            base_url="https://docs.example.com/llms.txt",
        )

        self.assertEqual(
            links,
            [
                {
                    "title": "First",
                    "url": "https://docs.example.com/guide/first.md",
                },
                {
                    "title": "External",
                    "url": "https://example.com/second.md",
                },
            ],
        )

    def test_validator_falls_back_to_content_hash(self):
        first = _response_validator(httpx.Response(200, content=b"first"))
        same = _response_validator(httpx.Response(200, content=b"first"))
        second = _response_validator(httpx.Response(200, content=b"second"))

        self.assertTrue(first.startswith("sha256:"))
        self.assertEqual(first, same)
        self.assertNotEqual(first, second)


class BundledDeploymentGuideTest(unittest.TestCase):
    def test_guide_is_packaged_as_a_searchable_generic_source(self):
        collected = collect_static_sources()
        self.assertEqual(set(collected), set(STATIC_SOURCES))

        content = collected["deployment_guide"]["raw_text"]
        self.assertNotIn("mock-coin", content.lower())
        self.assertNotIn("MOCKCOIN_", content)
        self.assertNotIn("0_84_0", content)
        self.assertIn("EXPECTED_API_HOST", content)

        chunks = chunk_all(collected)
        results = search(
            chunks,
            "ait deploy 검토 요청",
            source="deployment_guide",
            max_results=30,
        )
        self.assertTrue(results)
        self.assertTrue(
            all(result["source"] == "deployment_guide" for result in results)
        )


class ChunkLimitTest(unittest.TestCase):
    def test_single_long_line_never_exceeds_chunk_limit(self):
        chunks = chunk_document(
            {
                "source": "test",
                "url": "https://example.com/long.md",
                "title": "Long line",
                "content": "# Long line\n" + ("x" * (MAX_CHUNK_LEN * 3 + 17)),
            }
        )

        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(chunk["content"]) <= MAX_CHUNK_LEN for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
