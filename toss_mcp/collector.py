"""토스 API 문서 수집기"""

import re
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

SOURCES = {
    "apps_in_toss": {
        "name": "앱인토스",
        "llms_url": "https://developers-apps-in-toss.toss.im/llms.txt",
        "type": "seed",  # llms.txt는 목차 → 하위 페이지 순회
    },
    "tds_react_native": {
        "name": "TDS React Native",
        "llms_url": "https://tossmini-docs.toss.im/tds-react-native/llms-full.txt",
        "type": "full",  # 통합 마크다운
    },
    "tds_mobile": {
        "name": "TDS Mobile",
        "llms_url": "https://tossmini-docs.toss.im/tds-mobile/llms-full.txt",
        "type": "full",
    },
}

TIMEOUT = 30
CONCURRENCY = 8


async def fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    """URL에서 텍스트를 다운로드한다. 실패 시 None 반환."""
    try:
        resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("fetch failed: %s → %s", url, e)
        return None


def parse_links(llms_txt: str) -> list[dict[str, str]]:
    """llms.txt에서 [제목](URL) 형태의 링크를 파싱한다."""
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
    results = []
    for match in pattern.finditer(llms_txt):
        title, url = match.group(1), match.group(2)
        results.append({"title": title, "url": url})
    return results


async def fetch_seed_pages(
    client: httpx.AsyncClient, links: list[dict[str, str]]
) -> list[dict]:
    """앱인토스 하위 페이지들을 병렬로 수집한다."""
    sem = asyncio.Semaphore(CONCURRENCY)
    documents = []

    async def _fetch_one(link: dict[str, str]):
        async with sem:
            text = await fetch_text(client, link["url"])
            if text:
                documents.append(
                    {
                        "source": "apps_in_toss",
                        "url": link["url"],
                        "title": link["title"],
                        "content": text,
                    }
                )

    await asyncio.gather(*[_fetch_one(link) for link in links])
    return documents


async def collect_all() -> dict:
    """모든 소스에서 문서를 수집한다. 반환: {source_key: {raw_text, documents}}"""
    result = {}
    async with httpx.AsyncClient() as client:
        for key, source in SOURCES.items():
            raw = await fetch_text(client, source["llms_url"])
            if raw is None:
                logger.error("소스 %s 수집 실패", key)
                continue

            if source["type"] == "full":
                # 통합 마크다운: 그대로 전달
                result[key] = {
                    "raw_text": raw,
                    "documents": [
                        {
                            "source": key,
                            "url": source["llms_url"],
                            "title": source["name"],
                            "content": raw,
                        }
                    ],
                }
            else:
                # seed: llms.txt 파싱 후 하위 페이지 순회
                links = parse_links(raw)
                logger.info("앱인토스 링크 %d개 발견", len(links))
                documents = await fetch_seed_pages(client, links)
                result[key] = {
                    "raw_text": raw,
                    "documents": documents,
                }

    logger.info(
        "수집 완료: %s",
        {k: len(v["documents"]) for k, v in result.items()},
    )
    return result


async def fetch_single_source_raw(url: str) -> str | None:
    """단일 URL의 원본 텍스트를 반환한다 (해시 비교용)."""
    async with httpx.AsyncClient() as client:
        return await fetch_text(client, url)


async def check_source_etags(
    stored_etags: dict[str, str],
) -> tuple[dict[str, str], bool]:
    """각 소스의 ETag를 확인하여 변경 여부를 판단한다.

    Returns:
        (new_etags, needs_refresh): 새 ETag 딕셔너리와 갱신 필요 여부
    """
    new_etags: dict[str, str] = {}
    changed = False

    async with httpx.AsyncClient() as client:
        for key, source in SOURCES.items():
            url = source["llms_url"]
            stored_etag = stored_etags.get(key)
            headers = {}
            if stored_etag:
                headers["If-None-Match"] = stored_etag

            try:
                resp = await client.get(
                    url, headers=headers, timeout=TIMEOUT, follow_redirects=True
                )

                if resp.status_code == 304:
                    # 서버가 304 반환 → 변경 없음
                    logger.info("ETag 304 (변경 없음): %s", key)
                    new_etags[key] = stored_etag  # type: ignore[assignment]
                    continue

                resp.raise_for_status()
                etag = resp.headers.get("etag")
                if etag:
                    new_etags[key] = etag
                    if stored_etag and etag == stored_etag:
                        # 서버가 304를 지원하지 않지만 ETag 동일 → 변경 없음
                        logger.info("ETag 일치 (변경 없음): %s", key)
                    else:
                        logger.info(
                            "ETag 불일치 (변경 감지): %s [%s → %s]",
                            key,
                            stored_etag,
                            etag,
                        )
                        changed = True
                else:
                    # ETag 없음 → 판단 불가, 안전하게 갱신
                    logger.info("ETag 없음 (갱신 필요): %s", key)
                    changed = True

            except Exception as e:
                logger.warning("ETag 확인 실패: %s → %s", key, e)
                changed = True

    return new_etags, changed


async def collect_etags() -> dict[str, str]:
    """모든 소스의 현재 ETag를 수집한다."""
    etags: dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        for key, source in SOURCES.items():
            try:
                resp = await client.get(
                    source["llms_url"], timeout=TIMEOUT, follow_redirects=True
                )
                resp.raise_for_status()
                etag = resp.headers.get("etag")
                if etag:
                    etags[key] = etag
                    logger.info("ETag 수집: %s → %s", key, etag)
                else:
                    logger.info("ETag 없음: %s", key)
            except Exception as e:
                logger.warning("ETag 수집 실패: %s → %s", key, e)
    return etags
