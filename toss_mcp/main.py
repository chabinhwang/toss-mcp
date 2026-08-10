"""토스 API 문서 검색 MCP 서버"""

import logging
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from .cache import (
    load_chunks,
    load_etags,
    save_chunks,
    save_etags,
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
from .icons import (
    ICON_USAGE_GUIDE,
    SUPPORTED_ICON_TYPES,
    get_item_usage_hint,
    load_icon_items,
    search_icon_catalog,
)
from .knowledge import STATIC_SOURCES, collect_static_sources
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
    """서버 시작 시 문서를 로드한다."""
    await _init_chunks()
    _init_icons()
    yield


mcp = MCPServer(
    "toss-docs",
    instructions=(
        "토스 공식 개발자 문서와 범용 앱인토스 배포 가이드 검색 "
        "+ 토스 아이콘 카탈로그 검색 도구"
    ),
    lifespan=lifespan,
)


@mcp.tool()
async def search_docs(
    query: str,
    source: str | None = None,
    max_results: int = 10,
) -> str:
    """토스 개발자 문서를 검색합니다.

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

    output_parts = []
    for i, r in enumerate(results, 1):
        output_parts.append(
            f"### 결과 {i} [{r['source']}]\n"
            f"**헤더**: {r['header']}\n"
            f"**URL**: {r['url']}\n"
            f"**매칭**: {r['match_count']}개 키워드 ({r['match_ratio']:.0%})\n\n"
            f"{r['content']}\n"
        )

    return "\n---\n".join(output_parts)


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

    parts.append("## 내장 보완 가이드")
    for source_key, source in STATIC_SOURCES.items():
        parts.append(
            f"### `{source_key}` — {source['name']}\n"
            f"- 현재 검색 청크: {chunk_counts[source_key]}개\n"
            f"- 식별자: {source['url']}"
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
