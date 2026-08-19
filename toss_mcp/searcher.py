"""키워드 기반 문서 검색"""

from .knowledge import FIELD_NOTES_SOURCE

MAX_RESULTS = 10


def _query_hits_triggers(query: str, triggers: list[str]) -> int:
    """쿼리와 겹치는 트리거 개수를 반환한다."""
    query_l = query.lower()
    hits = 0
    for trigger in triggers:
        needle = trigger.lower().strip()
        if not needle:
            continue
        if needle in query_l or needle.replace("-", " ") in query_l:
            hits += 1
    return hits


def _should_inject_field_note(source: str | None, chunk: dict) -> bool:
    if chunk.get("source") != FIELD_NOTES_SOURCE:
        return False
    # 소스 필터가 없으면 모든 현장 노트를 후보로 둔다. 실제 주입은 트리거 매칭이 있을 때만 한다.
    if source is None or source == FIELD_NOTES_SOURCE:
        return True
    related = chunk.get("related_sources") or []
    return source in related


def _result_entry(
    chunk: dict, match_count: int, keyword_count: int, injected: bool
) -> dict:
    return {
        "source": chunk["source"],
        "url": chunk["url"],
        "header": chunk["header"],
        "content": chunk["content"],
        "match_count": match_count,
        "match_ratio": (match_count / keyword_count) if keyword_count else 1.0,
        "status": chunk.get("status"),
        "citations": chunk.get("citations") or [],
        "as_of": chunk.get("as_of"),
        "injected": injected,
    }


def _keyword_search(candidates: list[dict], keywords: list[str]) -> list[dict]:
    exact_matches = []
    partial_matches = []

    for chunk in candidates:
        searchable = (chunk["header"] + " " + chunk["content"]).lower()
        matched = [kw for kw in keywords if kw in searchable]
        match_count = len(matched)

        if match_count == 0:
            continue

        entry = _result_entry(chunk, match_count, len(keywords), injected=False)
        if match_count == len(keywords):
            exact_matches.append(entry)
        else:
            partial_matches.append(entry)

    exact_matches.sort(key=lambda item: -item["match_count"])
    partial_matches.sort(key=lambda item: -item["match_count"])
    return exact_matches + partial_matches


def _result_key(item: dict) -> tuple[str, str, str]:
    return (item["source"], item["url"], item["header"])


def _inject_field_notes(
    chunks: list[dict],
    query: str,
    source: str | None,
    keyword_results: list[dict],
) -> list[dict]:
    """관련 현장 노트를 키워드 결과 맨 앞으로 올린다.

    본문에 같은 키워드가 있어 이미 검색된 노트도 공식 청크에 밀리지 않게
    다시 앞으로 당긴다.
    """
    trigger_notes: list[tuple[dict, int]] = []
    for chunk in chunks:
        if not _should_inject_field_note(source, chunk):
            continue
        trigger_hits = _query_hits_triggers(query, chunk.get("triggers") or [])
        if trigger_hits:
            trigger_notes.append((chunk, trigger_hits))
    trigger_notes.sort(key=lambda item: -item[1])

    keyword_by_key = {_result_key(item): item for item in keyword_results}
    boosted: list[dict] = []
    boosted_keys: set[tuple[str, str, str]] = set()

    for chunk, trigger_hits in trigger_notes:
        key = _result_key(chunk)
        existing = keyword_by_key.get(key)
        if existing is not None:
            boosted.append({**existing, "injected": True})
        else:
            boosted.append(
                _result_entry(chunk, trigger_hits, trigger_hits, injected=True)
            )
        boosted_keys.add(key)

    rest = [item for item in keyword_results if _result_key(item) not in boosted_keys]
    return boosted + rest


def search(
    chunks: list[dict],
    query: str,
    source: str | None = None,
    max_results: int = MAX_RESULTS,
) -> list[dict]:
    """키워드 매칭으로 청크를 검색한다.

    - 모든 키워드 포함 → 정확 매칭 (우선순위 높음)
    - 일부 키워드 포함 → 부분 매칭 (폴백)
    - source 필터 지원: 청크의 source 키와 정확히 일치하는 소스
    - 앱인토스 관련 쿼리가 현장 노트 트리거와 겹치면 해당 노트를 함께 반환
    """
    keywords = query.lower().split()
    if not keywords:
        return []

    candidates = chunks
    if source:
        candidates = [chunk for chunk in candidates if chunk["source"] == source]

    results = _keyword_search(candidates, keywords)
    results = _inject_field_notes(chunks, query, source, results)
    return results[:max_results]
