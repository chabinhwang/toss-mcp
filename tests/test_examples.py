import io
import json
import tarfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from toss_mcp import main as mcp_main
from toss_mcp.example_chunker import chunk_example_files
from toss_mcp.example_collector import (
    APACHE_LICENSE_MARKERS,
    ExampleSourceError,
    is_selected_example_path,
    parse_example_archive,
)
from toss_mcp.example_searcher import list_example_summaries, search_examples
from toss_mcp.examples import refresh_example_snapshot


def _archive(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, content in files.items():
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(path)
            info.size = len(encoded)
            archive.addfile(info, io.BytesIO(encoded))
    return buffer.getvalue()


class ExamplePathSelectionTest(unittest.TestCase):
    def test_selects_searchable_source_files_only(self):
        selected = {
            "growth/README.md",
            "growth/package.json",
            "growth/apps-in-toss.config.ts",
            "growth/src/App.tsx",
            "in-app-ads/src/ads/policy.test.ts",
            "examples/pages/index.tsx",
            "toss-login/server/src/app.js",
            "toss-login/server/server.js",
        }
        excluded = {
            "growth/public/appsintoss-logo.png",
            "growth/package-lock.json",
            "growth/src/App.css",
            "growth/src/vite-env.d.ts",
            "examples/src/router.gen.ts",
            "examples/.yarn/sdks/typescript/lib/typescript.js",
            "toss-login/server/.env.server",
            "toss-login/server/cert/mock_private.key",
            "assets/tags/tag-webview.svg",
        }

        self.assertTrue(all(is_selected_example_path(path) for path in selected))
        self.assertTrue(all(not is_selected_example_path(path) for path in excluded))


class ExampleArchiveTest(unittest.TestCase):
    def test_parses_allowlisted_files_and_preserves_provenance(self):
        license_text = "\n".join(APACHE_LICENSE_MARKERS)
        archive = _archive(
            {
                "apps-in-toss-examples-sha/LICENSE": license_text,
                "apps-in-toss-examples-sha/NOTICE": "Toss example notice",
                "apps-in-toss-examples-sha/growth/package.json": json.dumps(
                    {
                        "name": "growth",
                        "dependencies": {
                            "@apps-in-toss/web-framework": "3.0.3",
                        },
                    }
                ),
                "apps-in-toss-examples-sha/growth/README.md": "# Growth\n\nGuide.",
                "apps-in-toss-examples-sha/growth/src/App.tsx": (
                    "export function App() {\n  return null;\n}\n"
                ),
                "apps-in-toss-examples-sha/growth/public/logo.png": "ignored",
                "apps-in-toss-examples-sha/growth/.env": "SECRET=ignored",
            }
        )

        snapshot = parse_example_archive(archive, "a" * 40)

        self.assertEqual(snapshot["license"], "Apache-2.0")
        self.assertEqual(snapshot["notice"], "Toss example notice")
        self.assertEqual(
            {item["path"] for item in snapshot["files"]},
            {"growth/package.json", "growth/README.md", "growth/src/App.tsx"},
        )
        source = next(
            item for item in snapshot["files"] if item["path"].endswith("App.tsx")
        )
        self.assertEqual(source["example"], "growth")
        self.assertEqual(
            source["sdk_packages"], {"@apps-in-toss/web-framework": "3.0.3"}
        )
        self.assertIn("/blob/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/", source["url"])

    def test_rejects_archive_without_apache_license(self):
        archive = _archive(
            {
                "apps-in-toss-examples-sha/LICENSE": "MIT License",
                "apps-in-toss-examples-sha/growth/src/App.tsx": "export const App = 1;",
            }
        )

        with self.assertRaises(ExampleSourceError):
            parse_example_archive(archive, "b" * 40)

    def test_rejects_path_traversal(self):
        archive = _archive(
            {
                "../LICENSE": "\n".join(APACHE_LICENSE_MARKERS),
                "../growth/src/App.tsx": "export const App = 1;",
            }
        )

        with self.assertRaises(ExampleSourceError):
            parse_example_archive(archive, "c" * 40)


class ExampleSearchTest(unittest.TestCase):
    def setUp(self):
        self.files = [
            {
                "path": "in-app-payments/src/hooks/useInAppPayments.ts",
                "content": (
                    'import { IAP } from "@apps-in-toss/web-framework";\n\n'
                    "export function useInAppPayments() {\n"
                    "  return IAP.getPendingOrders();\n"
                    "}\n"
                ),
                "example": "in-app-payments",
                "language": "typescript",
                "url": "https://github.com/toss/apps-in-toss-examples/blob/sha/file.ts",
                "sdk_packages": {"@apps-in-toss/web-framework": "3.0.3"},
            },
            {
                "path": "in-app-payments/README.md",
                "content": (
                    "# 인앱 결제 예제\n\n"
                    "getPendingOrders로 미결 주문을 안전하게 복원해요."
                ),
                "example": "in-app-payments",
                "language": "markdown",
                "url": "https://github.com/toss/apps-in-toss-examples/blob/sha/README.md",
                "sdk_packages": {"@apps-in-toss/web-framework": "3.0.3"},
            },
        ]
        self.chunks = chunk_example_files(self.files, "d" * 40)

    def test_chunks_preserve_path_lines_commit_and_license(self):
        code = next(chunk for chunk in self.chunks if chunk["language"] == "typescript")

        self.assertEqual(code["commit"], "d" * 40)
        self.assertEqual(code["license"], "Apache-2.0")
        self.assertGreaterEqual(code["start_line"], 1)
        self.assertGreaterEqual(code["end_line"], code["start_line"])
        self.assertEqual(code["path"], self.files[0]["path"])

    def test_search_prioritizes_symbol_and_sdk_code(self):
        results = search_examples(
            self.chunks,
            "getPendingOrders",
            example="in-app-payments",
        )

        self.assertTrue(results)
        self.assertEqual(results[0]["language"], "typescript")
        self.assertIn("getPendingOrders", results[0]["content"])

    def test_lists_example_summary_with_sdk_version(self):
        summaries = list_example_summaries(self.files)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["example"], "in-app-payments")
        self.assertEqual(summaries[0]["title"], "인앱 결제 예제")
        self.assertEqual(
            summaries[0]["sdk_packages"],
            {"@apps-in-toss/web-framework": "3.0.3"},
        )


class ExampleRefreshTest(unittest.IsolatedAsyncioTestCase):
    def _source_archive(self) -> bytes:
        return _archive(
            {
                "apps-in-toss-examples-sha/LICENSE": "\n".join(APACHE_LICENSE_MARKERS),
                "apps-in-toss-examples-sha/growth/package.json": json.dumps(
                    {
                        "name": "growth",
                        "dependencies": {
                            "@apps-in-toss/web-framework": "3.0.3",
                        },
                    }
                ),
                "apps-in-toss-examples-sha/growth/src/App.tsx": (
                    "export const App = () => null;\n"
                ),
            }
        )

    async def test_refreshes_changed_commit_and_reuses_304_cache(self):
        commit = "e" * 40
        archive = self._source_archive()

        def first_handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.github.com":
                return httpx.Response(
                    200,
                    json={"sha": commit},
                    headers={"etag": '"example-etag"'},
                )
            return httpx.Response(200, content=archive)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(first_handler)
        ) as client:
            snapshot, updated = await refresh_example_snapshot(None, client=client)

        self.assertTrue(updated)
        self.assertEqual(snapshot["manifest"]["commit"], commit)
        self.assertEqual(snapshot["manifest"]["license"], "Apache-2.0")
        self.assertTrue(snapshot["chunks"])

        def second_handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers.get("if-none-match"), '"example-etag"')
            return httpx.Response(304)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(second_handler)
        ) as client:
            reused, updated = await refresh_example_snapshot(snapshot, client=client)

        self.assertFalse(updated)
        self.assertIs(reused, snapshot)

    async def test_startup_keeps_last_valid_cache_when_refresh_fails(self):
        cached = {
            "manifest": {"commit": "f" * 40},
            "files": [{"path": "growth/README.md"}],
            "chunks": [{"content": "cached"}],
            "notice": None,
        }
        with (
            patch.object(mcp_main, "load_example_snapshot", return_value=cached),
            patch.object(
                mcp_main,
                "refresh_example_snapshot",
                AsyncMock(side_effect=ExampleSourceError("invalid upstream")),
            ),
        ):
            status = await mcp_main._init_examples()

        self.assertIn("기존 검증 캐시 유지", status)
        self.assertIs(mcp_main._example_state, cached)


if __name__ == "__main__":
    unittest.main()
