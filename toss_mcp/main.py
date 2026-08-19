"""토스 공식 문서·아이콘·예제 검색 MCP 서버."""

import asyncio
import logging
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from .cache import (
    load_chunks,
    load_etags,
    load_example_snapshot,
    save_chunks,
    save_etags,
    save_example_snapshot,
    update_hashes,
)
from .chunker import chunk_all
from .collector import (
    SOURCES,
    check_source_etags,
    collect_all,
    collect_etags,
    source_urls,
)
from .example_searcher import (
    list_example_summaries,
)
from .example_searcher import (
    search_examples as search_example_chunks,
)
from .examples import refresh_example_snapshot
from .icons import (
    ICON_USAGE_GUIDE,
    SUPPORTED_ICON_TYPES,
    get_item_usage_hint,
    load_icon_items,
    search_icon_catalog,
)
from .knowledge import FIELD_NOTES_SOURCE, STATIC_SOURCES, collect_static_sources
from .searcher import search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# 전역 청크 저장소
_chunks: list[dict] = []
_icon_items: list[dict] = []
_example_state: dict = {"manifest": {}, "files": [], "chunks": [], "notice": None}


def _build_official_chunks(
    collected: dict,
    cached: list[dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """새 수집 결과를 청킹하고 실패한 소스는 기존 캐시로 보완한다."""
    fresh_chunks = chunk_all(collected)
    missing_sources = sorted(set(SOURCES) - set(collected))

    if cached and missing_sources:
        fallback_chunks = [
            chunk for chunk in cached if chunk.get("source") in missing_sources
        ]
        fresh_chunks.extend(fallback_chunks)
        logger.warning(
            "수집 실패 소스를 기존 캐시로 보완: %s (%d개 청크)",
            ", ".join(missing_sources),
            len(fallback_chunks),
        )

    return fresh_chunks, missing_sources


def _activate_chunks(official_chunks: list[dict]) -> None:
    """공식 청크와 패키지 내장 가이드를 검색 대상으로 활성화한다."""
    global _chunks
    static_chunks = chunk_all(collect_static_sources())
    _chunks = official_chunks + static_chunks
    logger.info(
        "검색 청크 활성화: 공식 %d개 + 내장 가이드 %d개",
        len(official_chunks),
        len(static_chunks),
    )


async def _init_chunks():
    """캐시 또는 수집으로 청크를 초기화한다."""
    cached = load_chunks()

    if cached:
        stored_validators = load_etags()

        if stored_validators:
            # 캐시 + validator 존재 → 공식 원천 변경 감지
            logger.info("공식 원천 validator 기반 변경 감지 시작...")
            new_validators, needs_refresh = await check_source_etags(stored_validators)

            if not needs_refresh:
                _activate_chunks(cached)
                logger.info("공식 원천 변경 없음, 캐시 사용: %d개 청크", len(_chunks))
                return

            # 변경 감지 → 전체 재수집
            logger.info("공식 원천 변경 감지, 문서 재수집 시작...")
            collected = await collect_all()
            official_chunks, _ = _build_official_chunks(collected, cached)
            save_chunks(official_chunks)
            raw_texts = {k: v["raw_text"] for k, v in collected.items()}
            update_hashes(raw_texts)
            save_etags(new_validators)
            _activate_chunks(official_chunks)
            logger.info("재수집 완료: %d개 청크", len(_chunks))
            return

        # 캐시 있지만 validator 없음 (이전 포맷) → 캐시 사용 + validator 저장
        _activate_chunks(cached)
        logger.info(
            "캐시에서 %d개 청크 로드 (validator 없음, 다음 기동용 수집)",
            len(_chunks),
        )
        validators = await collect_etags()
        if validators:
            save_etags(validators)
        return

    # 캐시 없음 → 전체 수집 + 청킹
    logger.info("캐시 없음, 문서 수집 시작...")
    collected = await collect_all()
    official_chunks, _ = _build_official_chunks(collected)

    save_chunks(official_chunks)
    raw_texts = {k: v["raw_text"] for k, v in collected.items()}
    update_hashes(raw_texts)
    validators = await collect_etags()
    if validators:
        save_etags(validators)
    _activate_chunks(official_chunks)
    logger.info("초기화 완료: %d개 청크", len(_chunks))


def _activate_examples(snapshot: dict) -> None:
    global _example_state
    _example_state = snapshot
    manifest = snapshot.get("manifest", {})
    logger.info(
        "공식 예제 활성화: commit=%s, 파일 %d개, 청크 %d개",
        manifest.get("commit", "unknown"),
        len(snapshot.get("files", [])),
        len(snapshot.get("chunks", [])),
    )


async def _init_examples(force: bool = False) -> str:
    """공식 예제 main의 최신 SHA를 확인하고 안전하게 캐시를 교체한다."""
    cached = load_example_snapshot()
    try:
        snapshot, updated = await refresh_example_snapshot(cached, force=force)
        if updated:
            save_example_snapshot(snapshot)
        _activate_examples(snapshot)
        commit = snapshot["manifest"]["commit"]
        return (
            f"공식 예제 업데이트 완료: {commit}"
            if updated
            else f"공식 예제 변경 없음: {commit}"
        )
    except Exception as exc:  # noqa: BLE001 - 마지막 검증 성공 캐시를 유지한다.
        logger.warning("공식 예제 최신화 실패: %s", exc)
        if cached:
            _activate_examples(cached)
            return (
                "공식 예제 최신화 실패, 기존 검증 캐시 유지: "
                f"{cached['manifest'].get('commit', 'unknown')}"
            )
        _activate_examples({"manifest": {}, "files": [], "chunks": [], "notice": None})
        return f"공식 예제를 로드하지 못했습니다: {exc}"


def _init_icons():
    """아이콘 카탈로그를 로드한다."""
    global _icon_items
    _icon_items = load_icon_items()
    if _icon_items:
        logger.info("아이콘 카탈로그 로드 완료: %d개", len(_icon_items))
    else:
        logger.warning("아이콘 카탈로그를 로드하지 못했습니다.")


@asynccontextmanager
async def lifespan(server: MCPServer):
    """서버 시작 시 문서와 공식 예제를 최신화한다."""
    await asyncio.gather(_init_chunks(), _init_examples())
    _init_icons()
    yield


mcp = MCPServer(
    "toss-docs",
    instructions=(
        "토스 공식 개발자 문서, 범용 앱인토스 배포 가이드, "
        "공식 문서에 없는 콘솔/담당자 확인 현장 노트 검색 "
        "+ 토스 아이콘 카탈로그와 Apache-2.0 공식 예제 검색 도구. "
        "send-message 이동 URL은 API의 landingUrl이 아니라 "
        "콘솔 URL의 {{ 변수 }}를 context로 치환한다. 관련 내용은 field_notes에 있다."
    ),
    lifespan=lifespan,
)


def _format_search_result(index: int, result: dict) -> str:
    lines = [f"### 결과 {index} [{result['source']}]"]
    if result["source"] == FIELD_NOTES_SOURCE:
        as_of = result.get("as_of")
        status = (
            "비공식 · 공식 문서 미기재 · 담당자 커뮤니티 확인 · 콘솔 저장 전 재확인"
        )
        if as_of:
            status += f" · {as_of} 기준"
        lines.append(f"**상태**: {status}")
    lines.append(f"**헤더**: {result['header']}")
    lines.append(f"**URL**: {result['url']}")
    citations = result.get("citations") or []
    if citations:
        lines.append("**근거**: " + " ".join(citations))
    if result.get("injected"):
        lines.append("**매칭**: 관련 현장 노트 (트리거)")
    else:
        lines.append(
            f"**매칭**: {result['match_count']}개 키워드 ({result['match_ratio']:.0%})"
        )
    lines.append("")
    lines.append(result["content"])
    return "\n".join(lines)


@mcp.tool()
async def search_docs(
    query: str,
    source: str | None = None,
    max_results: int = 10,
) -> str:
    """토스 개발자 문서와 내장 보완 자료를 검색합니다.

    공식 스펙에 없는 콘솔/담당자 확인 동작(send-message 이동 URL의
    `{{ 변수 }}` 치환 등)은 field_notes에 있습니다. apps_in_toss만
    필터해도 관련 현장 노트는 함께 반환됩니다.

    Args:
        query: 검색어 (공백으로 구분된 키워드)
        source: 소스 필터 (선택). list_sources 도구에서 지원값 확인
        max_results: 최대 결과 수 (기본 10, 최대 30)
    """
    if not _chunks:
        return "문서가 아직 로드되지 않았습니다. sync_sources를 호출해 주세요."

    if not query.strip():
        return "query는 비어 있을 수 없습니다."

    supported_sources = set(SOURCES) | set(STATIC_SOURCES)
    if source and source not in supported_sources:
        return (
            "지원하지 않는 source입니다. "
            f"지원값: {', '.join(sorted(supported_sources))}"
        )

    if max_results < 1:
        return "max_results는 1 이상이어야 합니다."
    max_results = min(max_results, 30)

    results = search(_chunks, query, source=source, max_results=max_results)
    if not results:
        return f"'{query}'에 대한 검색 결과가 없습니다."

    return "\n---\n".join(
        _format_search_result(index, result) for index, result in enumerate(results, 1)
    )


@mcp.tool()
async def list_sources() -> str:
    """검색 가능한 공식/내장 문서 소스와 원천 URL을 보여줍니다."""
    chunk_counts = {
        source_key: sum(1 for chunk in _chunks if chunk.get("source") == source_key)
        for source_key in set(SOURCES) | set(STATIC_SOURCES)
    }

    parts = ["## 공식 원천"]
    for source_key, source in SOURCES.items():
        parts.append(
            f"### `{source_key}` — {source['name']}\n"
            f"- 수집 방식: `{source['collection_type']}`\n"
            f"- 현재 검색 청크: {chunk_counts[source_key]}개\n"
            + "\n".join(f"- {role}: {url}" for role, url in source_urls(source))
        )

    guide_sources = [
        (source_key, source)
        for source_key, source in STATIC_SOURCES.items()
        if source.get("kind") != "field_notes"
    ]
    note_sources = [
        (source_key, source)
        for source_key, source in STATIC_SOURCES.items()
        if source.get("kind") == "field_notes"
    ]

    if guide_sources:
        parts.append("## 내장 보완 가이드")
        for source_key, source in guide_sources:
            parts.append(
                f"### `{source_key}` — {source['name']}\n"
                f"- 현재 검색 청크: {chunk_counts[source_key]}개\n"
                f"- 식별자: {source['url']}"
            )

    if note_sources:
        parts.append("## 현장 노트 (비공식 · 공식 문서 미기재)")
        for source_key, source in note_sources:
            description = source.get("description", "")
            extra = f"\n- {description}" if description else ""
            parts.append(
                f"### `{source_key}` — {source['name']}\n"
                f"- 현재 검색 청크: {chunk_counts[source_key]}개\n"
                f"- 식별자: {source['url']}"
                f"{extra}"
            )

    return "\n\n".join(parts)


@mcp.tool()
async def sync_sources(force: bool = False) -> str:
    """문서를 수동으로 동기화합니다.

    Args:
        force: True이면 캐시를 무시하고 강제 재수집
    """
    if force:
        logger.info("강제 동기화 시작")
        cached = load_chunks()
        collected = await collect_all()
        official_chunks, missing_sources = _build_official_chunks(collected, cached)
        raw_texts = {key: value["raw_text"] for key, value in collected.items()}

        save_chunks(official_chunks)
        if raw_texts:
            update_hashes(raw_texts)
        validators = await collect_etags()
        if validators:
            save_etags(validators)
        _activate_chunks(official_chunks)

        partial = (
            f" (수집 실패 소스는 가능한 기존 캐시 유지: {', '.join(missing_sources)})"
            if missing_sources
            else ""
        )
        return f"강제 동기화 완료: {len(_chunks)}개 청크{partial}"
    else:
        await _init_chunks()
        return f"동기화 완료: {len(_chunks)}개 청크"


def _example_attribution(manifest: dict) -> str:
    attribution = (
        "\n\n---\n"
        f"원천: {manifest.get('source_url', 'unknown')}  \n"
        f"커밋: `{manifest.get('commit', 'unknown')}`  \n"
        "라이선스: Apache-2.0  \n"
        "가공: toss-mcp가 검색을 위해 파일을 선별하고 청킹함"
    )
    notice = _example_state.get("notice")
    if notice:
        attribution += f"\n\n업스트림 NOTICE:\n```text\n{notice}\n```"
    return attribution


@mcp.tool()
async def list_examples(platform: str | None = None) -> str:
    """검색 가능한 Apps in Toss 공식 예제 목록을 보여줍니다.

    Args:
        platform: 플랫폼 필터 (선택). webview, react_native, server
    """
    files = _example_state.get("files", [])
    manifest = _example_state.get("manifest", {})
    if not files:
        return "공식 예제가 아직 로드되지 않았습니다. sync_examples를 호출해 주세요."

    supported_platforms = {"webview", "react_native", "server"}
    if platform and platform not in supported_platforms:
        return "지원하지 않는 platform입니다. 지원값: react_native, server, webview"

    summaries = list_example_summaries(files)
    if platform:
        summaries = [item for item in summaries if platform in item["platforms"]]
    if not summaries:
        return f"platform={platform} 조건에 맞는 공식 예제가 없습니다."

    parts = []
    for item in summaries:
        sdk = (
            ", ".join(
                f"`{name}@{version}`" for name, version in item["sdk_packages"].items()
            )
            or "확인된 SDK 없음"
        )
        parts.append(
            f"### `{item['example']}` — {item['title']}\n"
            f"- 플랫폼: {', '.join(item['platforms']) or '기타'}\n"
            f"- 파일: {item['file_count']}개\n"
            f"- SDK: {sdk}\n"
            + (f"- 설명: {item['summary']}" if item["summary"] else "")
        )
    return "\n\n".join(parts) + _example_attribution(manifest)


@mcp.tool()
async def search_examples(
    query: str,
    example: str | None = None,
    language: str | None = None,
    max_results: int = 5,
) -> str:
    """Apps in Toss 공식 예제 코드와 README를 검색합니다.

    Args:
        query: API, 함수, 기능 또는 코드 키워드
        example: 예제 ID 필터 (선택). list_examples에서 확인
        language: 언어 필터 (선택). markdown, json, typescript, tsx, javascript, jsx
        max_results: 최대 결과 수 (기본 5, 최대 20)
    """
    chunks = _example_state.get("chunks", [])
    manifest = _example_state.get("manifest", {})
    if not chunks:
        return "공식 예제가 아직 로드되지 않았습니다. sync_examples를 호출해 주세요."
    if not query.strip():
        return "query는 비어 있을 수 없습니다."
    supported_languages = {
        "markdown",
        "json",
        "typescript",
        "tsx",
        "javascript",
        "jsx",
    }
    if language and language not in supported_languages:
        return "지원하지 않는 language입니다."
    if max_results < 1:
        return "max_results는 1 이상이어야 합니다."

    results = search_example_chunks(
        chunks,
        query=query,
        example=example,
        language=language,
        max_results=min(max_results, 20),
    )
    if not results:
        return f"'{query}' 조건에 맞는 공식 예제가 없습니다."

    parts = []
    for index, result in enumerate(results, 1):
        sdk = (
            ", ".join(
                f"{name}@{version}" for name, version in result["sdk_packages"].items()
            )
            or "없음"
        )
        parts.append(
            f"### 결과 {index} — `{result['header']}`\n"
            f"- 예제: `{result['example']}`\n"
            f"- 파일: `{result['path']}:{result['start_line']}`\n"
            f"- 언어: `{result['language']}`\n"
            f"- SDK: {sdk}\n"
            f"- 원본: {result['url']}\n\n"
            f"````{result['language']}\n{result['content']}\n````"
        )
    return "\n\n---\n\n".join(parts) + _example_attribution(manifest)


@mcp.tool()
async def get_example_file(
    path: str,
    start_line: int = 1,
    end_line: int = 200,
) -> str:
    """선별된 공식 예제 파일의 지정 줄 범위를 조회합니다.

    Args:
        path: search_examples가 반환한 저장소 상대 경로
        start_line: 시작 줄 (1부터 시작)
        end_line: 끝 줄 (포함, 한 번에 최대 400줄)
    """
    files = _example_state.get("files", [])
    manifest = _example_state.get("manifest", {})
    file = next((item for item in files if item["path"] == path), None)
    if file is None:
        return f"선별된 공식 예제에서 파일을 찾지 못했습니다: {path}"
    if start_line < 1 or end_line < start_line:
        return "줄 범위가 올바르지 않습니다."
    if end_line - start_line + 1 > 400:
        return "한 번에 최대 400줄까지 조회할 수 있습니다."

    lines = file["content"].splitlines()
    if start_line > len(lines):
        return f"start_line이 파일 길이({len(lines)}줄)를 초과합니다."
    actual_end = min(end_line, len(lines))
    content = "\n".join(lines[start_line - 1 : actual_end])
    return (
        f"## `{path}:{start_line}-{actual_end}`\n"
        f"원본: {file['url']}\n\n"
        f"````{file['language']}\n{content}\n````" + _example_attribution(manifest)
    )


@mcp.tool()
async def sync_examples(force: bool = False) -> str:
    """Apps in Toss 공식 예제 main의 최신 커밋을 확인합니다.

    Args:
        force: True이면 같은 commit이어도 다시 다운로드하고 검증
    """
    status = await _init_examples(force=force)
    return (
        f"{status}\n"
        f"파일 {len(_example_state.get('files', []))}개, "
        f"청크 {len(_example_state.get('chunks', []))}개, 라이선스 Apache-2.0"
    )


@mcp.tool()
async def search_icons(
    query: str, icon_type: str | None = None, max_results: int = 10
) -> str:
    """토스 아이콘 카탈로그를 검색하고 타입별 추천 사용 코드를 안내합니다.

    Args:
        query: 검색어 (아이콘 이름/URL 일부)
        icon_type: 타입 필터 (선택). "icon-*", "icn-*", "emoji/image"
        max_results: 최대 결과 수 (기본 10, 최대 30)
    """
    if not _icon_items:
        return (
            "아이콘 카탈로그가 로드되지 않았습니다. "
            "toss_mcp/data/toss_icons.json 파일을 확인해 주세요."
        )

    if not query.strip():
        return "query는 비어 있을 수 없습니다."

    normalized_icon_type = icon_type.lower() if icon_type else None
    supported_types = {value.lower(): value for value in SUPPORTED_ICON_TYPES}
    if normalized_icon_type and normalized_icon_type not in supported_types:
        return (
            f"지원하지 않는 icon_type입니다. 지원값: {', '.join(SUPPORTED_ICON_TYPES)}"
        )

    if max_results < 1:
        return "max_results는 1 이상이어야 합니다."
    max_results = min(max_results, 30)

    results = search_icon_catalog(
        _icon_items,
        query=query,
        icon_type=normalized_icon_type,
        max_results=max_results,
    )
    if not results:
        filter_text = f", type={icon_type}" if icon_type else ""
        return f"'{query}'{filter_text} 조건에 대한 아이콘 검색 결과가 없습니다."

    output_parts = []
    for i, item in enumerate(results, 1):
        output_parts.append(
            f"### 결과 {i}\n"
            f"- **이름**: `{item['name']}`\n"
            f"- **타입**: `{item['type']}`\n"
            f"- **소스(URL)**: {item['src']}\n"
            f"- **매칭**: {item['match_count']}개 키워드 ({item['match_ratio']:.0%})\n"
            f"- **권장 사용**: {get_item_usage_hint(item)}\n"
        )

    return (
        f"'{query}' 아이콘 검색 결과 {len(results)}개\n\n"
        + "\n".join(output_parts)
        + "\n"
        + ICON_USAGE_GUIDE
    )


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
