"""공식 예제 최신성 확인과 재현 가능한 선별 스냅샷 구성."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from .example_chunker import chunk_example_files
from .example_collector import (
    DEFAULT_REF,
    REPOSITORY,
    REPOSITORY_URL,
    ExampleSourceError,
    fetch_example_archive,
    fetch_latest_commit,
    parse_example_archive,
)

EXAMPLE_SCHEMA_VERSION = 1


def _cached_commit(cached: dict | None) -> str | None:
    if not cached:
        return None
    manifest = cached.get("manifest", {})
    commit = manifest.get("commit")
    return commit if isinstance(commit, str) else None


def _cached_etag(cached: dict | None) -> str | None:
    if not cached:
        return None
    etag = cached.get("manifest", {}).get("etag")
    return etag if isinstance(etag, str) else None


async def refresh_example_snapshot(
    cached: dict | None,
    force: bool = False,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict, bool]:
    """main의 최신 SHA를 확인하고 변경됐을 때만 새 스냅샷을 만든다."""
    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    cache_compatible = bool(
        cached
        and cached.get("manifest", {}).get("schema_version") == EXAMPLE_SCHEMA_VERSION
    )
    requires_rebuild = force or not cache_compatible
    try:
        latest = await fetch_latest_commit(
            active_client,
            etag=None if requires_rebuild else _cached_etag(cached),
        )
        if latest["not_modified"]:
            if cached is None:
                raise ExampleSourceError("304 응답에 대응할 기존 예제 캐시가 없습니다.")
            return cached, False

        commit = latest["sha"]
        if (
            not requires_rebuild
            and cached is not None
            and commit == _cached_commit(cached)
        ):
            return cached, False

        archive = await fetch_example_archive(active_client, commit)
        parsed = parse_example_archive(archive, commit)
        chunks = chunk_example_files(parsed["files"], commit)
        snapshot = {
            "manifest": {
                "schema_version": EXAMPLE_SCHEMA_VERSION,
                "repository": REPOSITORY,
                "ref": DEFAULT_REF,
                "commit": commit,
                "etag": latest.get("etag"),
                "license": parsed["license"],
                "source_url": f"{REPOSITORY_URL}/tree/{commit}",
                "snapshot_created_at": datetime.now(UTC).isoformat(),
                "file_count": len(parsed["files"]),
                "chunk_count": len(chunks),
                "notice_present": parsed["notice"] is not None,
                "modified": "allowlist selection and search chunking by toss-mcp",
            },
            "files": parsed["files"],
            "chunks": chunks,
            "notice": parsed["notice"],
        }
        return snapshot, True
    finally:
        if owns_client:
            await active_client.aclose()
