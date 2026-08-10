"""토스 공식 개발자 문서 수집기."""

import asyncio
import hashlib
import logging
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

# 한 문서군에 index와 full 원천이 모두 있으면 둘 다 변경 감지에 사용한다.
# 실제 검색 문서는 중복을 피하기 위해 collection_type에 맞는 한 경로만 수집한다.
SOURCES = {
    "apps_in_toss": {
        "name": "앱인토스",
        "index_url": "https://developers-apps-in-toss.toss.im/llms.txt",
        "full_url": "https://developers-apps-in-toss.toss.im/llms-full.txt",
        "collection_type": "seed",
    },
    "tds_react_native": {
        "name": "TDS React Native",
        "index_url": "https://tossmini-docs.toss.im/tds-react-native/llms.txt",
        "full_url": "https://tossmini-docs.toss.im/tds-react-native/llms-full.txt",
        "collection_type": "full",
    },
    "tds_mobile": {
        "name": "TDS Mobile",
        "index_url": "https://tossmini-docs.toss.im/tds-mobile/llms.txt",
        "full_url": "https://tossmini-docs.toss.im/tds-mobile/llms-full.txt",
        "collection_type": "full",
    },
}

TIMEOUT = 30
CONCURRENCY = 8


def source_urls(source: dict) -> list[tuple[str, str]]:
    """소스 설정에 등록된 (역할, URL)을 중복 없이 반환한다."""
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()
    for role in ("index", "full"):
        url = source.get(f"{role}_url")
        if url and url not in seen:
            urls.append((role, url))
            seen.add(url)
    return urls


def source_validator_key(source_key: str, role: str) -> str:
    """캐시에 저장할 원천별 validator 키를 만든다."""
    return f"{source_key}:{role}"


async def fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    """URL에서 텍스트를 다운로드한다. 실패 시 None을 반환한다."""
    try:
        resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        logger.warning("fetch failed: %s → %s", url, exc)
        return None


def parse_links(llms_txt: str, base_url: str | None = None) -> list[dict[str, str]]:
    """llms.txt에서 Markdown 링크를 파싱하고 중복 URL을 제거한다."""
    pattern = re.compile(r"\[([^\]]+)\]\(([^\s\)]+)\)")
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in pattern.finditer(llms_txt):
        title, raw_url = match.group(1), match.group(2)
        if raw_url.startswith("#"):
            continue
        url = urljoin(base_url, raw_url) if base_url else raw_url
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        results.append({"title": title, "url": url})
        seen.add(url)

    return results


async def fetch_seed_pages(
    client: httpx.AsyncClient,
    source_key: str,
    links: list[dict[str, str]],
) -> list[dict]:
    """llms.txt가 가리키는 하위 페이지들을 순서를 보존해 병렬 수집한다."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _fetch_one(link: dict[str, str]) -> dict | None:
        async with sem:
            text = await fetch_text(client, link["url"])
            if text is None:
                return None
            return {
                "source": source_key,
                "url": link["url"],
                "title": link["title"],
                "content": text,
            }

    fetched = await asyncio.gather(*[_fetch_one(link) for link in links])
    return [document for document in fetched if document is not None]


async def _collect_source(
    client: httpx.AsyncClient,
    source_key: str,
    source: dict,
) -> tuple[str, dict] | None:
    """단일 문서군을 설정된 방식으로 수집한다."""
    collection_type = source["collection_type"]
    index_url = source.get("index_url")
    full_url = source.get("full_url")

    if collection_type == "full":
        if not full_url:
            logger.error("full 원천이 설정되지 않음: %s", source_key)
            return None
        raw = await fetch_text(client, full_url)
        if raw is None:
            logger.error("소스 %s 수집 실패", source_key)
            return None
        return source_key, {
            "raw_text": raw,
            "documents": [
                {
                    "source": source_key,
                    "url": full_url,
                    "title": source["name"],
                    "content": raw,
                }
            ],
        }

    if not index_url:
        logger.error("index 원천이 설정되지 않음: %s", source_key)
        return None

    raw_index = await fetch_text(client, index_url)
    if raw_index is not None:
        links = parse_links(raw_index, base_url=index_url)
        logger.info("%s 링크 %d개 발견", source_key, len(links))
        documents = await fetch_seed_pages(client, source_key, links)
        if links and len(documents) == len(links):
            return source_key, {
                "raw_text": raw_index,
                "documents": documents,
            }
        logger.warning(
            "%s 하위 페이지 수집 불완전 (%d/%d), full 원천으로 폴백",
            source_key,
            len(documents),
            len(links),
        )

    if full_url:
        raw_full = await fetch_text(client, full_url)
        if raw_full is not None:
            return source_key, {
                "raw_text": raw_full,
                "documents": [
                    {
                        "source": source_key,
                        "url": full_url,
                        "title": source["name"],
                        "content": raw_full,
                    }
                ],
            }

    logger.error("소스 %s의 index/full 원천을 모두 수집하지 못함", source_key)
    return None


async def collect_all() -> dict:
    """모든 공식 소스를 병렬 수집한다."""
    async with httpx.AsyncClient() as client:
        collected = await asyncio.gather(
            *[
                _collect_source(client, source_key, source)
                for source_key, source in SOURCES.items()
            ]
        )

    result = dict(item for item in collected if item is not None)
    logger.info(
        "수집 완료: %s",
        {key: len(value["documents"]) for key, value in result.items()},
    )
    return result


def _response_validator(resp: httpx.Response) -> str:
    """ETag가 없는 공식 원천도 비교할 수 있는 안정적인 validator를 만든다."""
    etag = resp.headers.get("etag")
    if etag:
        return f"etag:{etag}"

    last_modified = resp.headers.get("last-modified")
    if last_modified:
        return f"last-modified:{last_modified}"

    digest = hashlib.sha256(resp.content).hexdigest()
    return f"sha256:{digest}"


def _conditional_headers(stored_validator: str | None) -> dict[str, str]:
    if not stored_validator:
        return {}
    if stored_validator.startswith("etag:"):
        return {"If-None-Match": stored_validator.removeprefix("etag:")}
    if stored_validator.startswith("last-modified:"):
        return {"If-Modified-Since": stored_validator.removeprefix("last-modified:")}
    return {}


async def _check_single_validator(
    client: httpx.AsyncClient,
    validator_key: str,
    url: str,
    stored_validator: str | None,
) -> tuple[str, str | None, bool]:
    """원천 하나의 validator를 비교한다."""
    try:
        resp = await client.get(
            url,
            headers=_conditional_headers(stored_validator),
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 304 and stored_validator:
            logger.info("validator 304 (변경 없음): %s", validator_key)
            return validator_key, stored_validator, False

        resp.raise_for_status()
        validator = _response_validator(resp)
        changed = validator != stored_validator
        logger.info(
            "validator %s: %s",
            "변경 감지" if changed else "일치",
            validator_key,
        )
        return validator_key, validator, changed
    except httpx.HTTPError as exc:
        logger.warning("validator 확인 실패: %s → %s", validator_key, exc)
        return validator_key, stored_validator, True


async def check_source_etags(
    stored_etags: dict[str, str],
) -> tuple[dict[str, str], bool]:
    """모든 index/full 원천의 validator를 확인해 변경 여부를 판단한다.

    함수명과 캐시 파일명은 이전 버전 호환을 위해 etag를 유지하지만, 실제 값은
    ETag → Last-Modified → SHA256 순서로 만든 validator다.
    """
    async with httpx.AsyncClient() as client:
        checks = await asyncio.gather(
            *[
                _check_single_validator(
                    client,
                    source_validator_key(source_key, role),
                    url,
                    stored_etags.get(source_validator_key(source_key, role)),
                )
                for source_key, source in SOURCES.items()
                for role, url in source_urls(source)
            ]
        )

    new_etags = {
        key: validator for key, validator, _ in checks if validator is not None
    }
    return new_etags, any(changed for _, _, changed in checks)


async def collect_etags() -> dict[str, str]:
    """모든 index/full 원천의 현재 validator를 수집한다."""
    async with httpx.AsyncClient() as client:
        checks = await asyncio.gather(
            *[
                _check_single_validator(
                    client,
                    source_validator_key(source_key, role),
                    url,
                    None,
                )
                for source_key, source in SOURCES.items()
                for role, url in source_urls(source)
            ]
        )

    return {key: validator for key, validator, _ in checks if validator is not None}
