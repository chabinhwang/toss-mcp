"""키워드 기반 문서 검색"""

import logging

logger = logging.getLogger(__name__)

MAX_RESULTS = 10


def search(
    chunks: list[dict],
    query: str,
    source: str | None = None,
    max_results: int = MAX_RESULTS,
) -> list[dict]:
    """키워드 매칭으로 청크를 검색한다.

    - 모든 키워드 포함 → 정확 매칭 (우선순위 높음)
    - 일부 키워드 포함 → 부분 매칭 (폴백)
    - source 필터 지원: "apps_in_toss", "tds_react_native", "tds_mobile"
    """
    keywords = query.lower().split()
    if not keywords:
        return []

    # source 필터 적용
    candidates = chunks
    if source:
        candidates = [c for c in candidates if c["source"] == source]

    exact_matches = []
    partial_matches = []

    for chunk in candidates:
        searchable = (chunk["header"] + " " + chunk["content"]).lower()
        matched = [kw for kw in keywords if kw in searchable]
        match_count = len(matched)

        if match_count == 0:
            continue

        entry = {
            "source": chunk["source"],
            "url": chunk["url"],
            "header": chunk["header"],
            "content": chunk["content"],
            "match_count": match_count,
            "match_ratio": match_count / len(keywords),
        }

        if match_count == len(keywords):
            exact_matches.append(entry)
        else:
            partial_matches.append(entry)

    # 정확 매칭 우선, 부분 매칭은 매칭 수 내림차순
    exact_matches.sort(key=lambda x: -x["match_count"])
    partial_matches.sort(key=lambda x: -x["match_count"])

    results = exact_matches + partial_matches
    return results[:max_results]
