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
from toss_mcp.knowledge import (
    FIELD_NOTES_SOURCE,
    STATIC_SOURCES,
    collect_static_sources,
    parse_frontmatter,
)
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


class FieldNotesTest(unittest.TestCase):
    def test_parse_frontmatter_reads_scalar_and_list_fields(self):
        meta, body = parse_frontmatter(
            """---
id: sample-note
title: Sample
triggers:
  - send-message
  - 이동 URL
---
# Sample

본문
"""
        )

        self.assertEqual(meta["id"], "sample-note")
        self.assertEqual(meta["triggers"], ["send-message", "이동 URL"])
        self.assertTrue(body.startswith("# Sample"))

    def test_send_message_note_is_packaged_with_community_citations(self):
        collected = collect_static_sources()
        self.assertIn(FIELD_NOTES_SOURCE, collected)

        documents = collected[FIELD_NOTES_SOURCE]["documents"]
        self.assertEqual(len(documents), 1)
        note = documents[0]
        citations = " ".join(note["citations"])
        self.assertIn("https://techchat-apps-in-toss.toss.im/t/url/3297", citations)
        self.assertIn(
            "https://techchat-apps-in-toss.toss.im/t/send-message-api-url/4354",
            citations,
        )
        self.assertIn("{{ productId }}", note["content"])
        self.assertIn("{{ orderId }}", note["content"])
        self.assertIn("landingUrl", note["content"])
        self.assertNotIn("---", note["content"].splitlines()[0])

        chunks = chunk_all(collected)
        note_chunks = [
            chunk for chunk in chunks if chunk["source"] == FIELD_NOTES_SOURCE
        ]
        self.assertTrue(note_chunks)
        self.assertIn("send-message", note_chunks[0]["triggers"])

    def test_landing_url_query_returns_the_field_note(self):
        chunks = chunk_all(collect_static_sources())
        results = search(chunks, "landingUrl", max_results=5)

        self.assertTrue(results)
        self.assertEqual(results[0]["source"], FIELD_NOTES_SOURCE)
        self.assertIn("3297", " ".join(results[0]["citations"]))

    def test_send_message_query_boosts_field_note_ahead_of_official_hits(self):
        note_chunks = chunk_all(
            {"field_notes": collect_static_sources()[FIELD_NOTES_SOURCE]}
        )
        official = [
            {
                "source": "apps_in_toss",
                "url": f"https://example.com/send-message-{index}",
                "header": "send-message",
                "content": "send-message API는 templateSetCode와 context만 받습니다.",
            }
            for index in range(20)
        ]

        results = search(
            official + note_chunks,
            "send-message",
            source="apps_in_toss",
            max_results=10,
        )

        self.assertTrue(results)
        self.assertEqual(results[0]["source"], FIELD_NOTES_SOURCE)
        self.assertTrue(results[0]["injected"])
        self.assertTrue(any(item["source"] == "apps_in_toss" for item in results))

        unfiltered = search(official + note_chunks, "send-message", max_results=10)
        self.assertEqual(unfiltered[0]["source"], FIELD_NOTES_SOURCE)
        self.assertTrue(unfiltered[0]["injected"])

    def test_unrelated_source_filter_does_not_inject_apps_in_toss_notes(self):
        note_chunks = chunk_all(
            {"field_notes": collect_static_sources()[FIELD_NOTES_SOURCE]}
        )
        tds = [
            {
                "source": "tds_mobile",
                "url": "https://example.com/tds",
                "header": "IconButton",
                "content": "IconButton 사용법",
            }
        ]

        results = search(
            tds + note_chunks,
            "send-message",
            source="tds_mobile",
            max_results=10,
        )

        self.assertTrue(all(item["source"] != FIELD_NOTES_SOURCE for item in results))


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
