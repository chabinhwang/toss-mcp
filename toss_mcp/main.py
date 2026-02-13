"""토스 API 문서 검색 MCP 서버"""

import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .collector import collect_all, fetch_single_source_raw, SOURCES
from .chunker import chunk_all
from .searcher import search
from .icons import (
    SUPPORTED_ICON_TYPES,
    ICON_USAGE_GUIDE,
    load_icon_items,
    search_icon_catalog,
    get_item_usage_hint,
)
from .cache import (
    load_chunks,
    save_chunks,
    update_hashes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 전역 청크 저장소
_chunks: list[dict] = []
_icon_items: list[dict] = []


async def _init_chunks():
    """캐시 또는 수집으로 청크를 초기화한다."""
    global _chunks

    # 1) 캐시가 있으면 즉시 로드 (빠른 기동 우선)
    cached = load_chunks()
    if cached:
        _chunks = cached
        logger.info("캐시에서 %d개 청크 로드 완료", len(_chunks))
        return

    # 2) 캐시 없음 → 전체 수집 + 청킹
    logger.info("캐시 없음, 문서 수집 시작...")
    collected = await collect_all()
    _chunks = chunk_all(collected)

    # 3) 캐시 저장 + 해시 갱신
    save_chunks(_chunks)
    raw_texts = {k: v["raw_text"] for k, v in collected.items()}
    update_hashes(raw_texts)
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
async def lifespan(server: FastMCP):
    """서버 시작 시 문서를 로드한다."""
    await _init_chunks()
    _init_icons()
    yield


mcp = FastMCP(
    "toss-docs",
    instructions="토스 개발자 문서 검색 + 토스 아이콘 카탈로그 검색 도구",
    lifespan=lifespan,
)


@mcp.tool()
async def search_docs(query: str, source: str | None = None) -> str:
    """토스 개발자 문서를 검색합니다.

    Args:
        query: 검색어 (공백으로 구분된 키워드)
        source: 소스 필터 (선택). "apps_in_toss", "tds_react_native", "tds_mobile"
    """
    if not _chunks:
        return "문서가 아직 로드되지 않았습니다. sync_sources를 호출해 주세요."

    results = search(_chunks, query, source=source)
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
async def sync_sources(force: bool = False) -> str:
    """문서를 수동으로 동기화합니다.

    Args:
        force: True이면 캐시를 무시하고 강제 재수집
    """
    global _chunks

    if force:
        logger.info("강제 동기화 시작")
        collected = await collect_all()
        _chunks = chunk_all(collected)

        raw_texts = {}
        for key, source in SOURCES.items():
            text = await fetch_single_source_raw(source["llms_url"])
            if text:
                raw_texts[key] = text

        save_chunks(_chunks)
        if raw_texts:
            update_hashes(raw_texts)
        return f"강제 동기화 완료: {len(_chunks)}개 청크"
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
            "지원하지 않는 icon_type입니다. "
            f"지원값: {', '.join(SUPPORTED_ICON_TYPES)}"
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
