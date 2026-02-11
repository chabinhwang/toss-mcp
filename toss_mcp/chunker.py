"""마크다운 문서를 청크로 분리한다."""

import re
import logging

logger = logging.getLogger(__name__)

MAX_CHUNK_LEN = 3000

# H1 ~ H3 분리용 패턴
H1_PATTERN = re.compile(r"^# ", re.MULTILINE)
H2_PATTERN = re.compile(r"^## ", re.MULTILINE)
H3_PATTERN = re.compile(r"^### ", re.MULTILINE)


def _extract_header(text: str) -> str:
    """청크 텍스트에서 첫 번째 헤더를 추출한다."""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _split_by_pattern(text: str, pattern: re.Pattern) -> list[str]:
    """정규식 패턴(헤더) 기준으로 텍스트를 분리한다."""
    positions = [m.start() for m in pattern.finditer(text)]
    if not positions:
        return [text]

    parts = []
    # 헤더 앞에 내용이 있으면 첫 파트로 추가
    if positions[0] > 0:
        preamble = text[: positions[0]].strip()
        if preamble:
            parts.append(preamble)

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        part = text[pos:end].strip()
        if part:
            parts.append(part)

    return parts


def _split_chunk(text: str) -> list[str]:
    """길이 초과 청크를 H2 → H3 순으로 추가 분할한다."""
    if len(text) <= MAX_CHUNK_LEN:
        return [text]

    # H2로 분할 시도
    parts = _split_by_pattern(text, H2_PATTERN)
    if len(parts) > 1:
        result = []
        for p in parts:
            result.extend(_split_chunk(p))
        return result

    # H3로 분할 시도
    parts = _split_by_pattern(text, H3_PATTERN)
    if len(parts) > 1:
        result = []
        for p in parts:
            result.extend(_split_chunk(p))
        return result

    # 헤더 없이 길면 줄바꿈 기준 강제 분할
    if len(text) > MAX_CHUNK_LEN:
        return _force_split(text)
    return [text]


def _force_split(text: str) -> list[str]:
    """헤더가 없는 긴 텍스트를 빈 줄 기준으로 강제 분할한다.
    빈 줄로도 분할이 안 되면 줄 단위로 분할한다."""
    paragraphs = re.split(r"\n\n+", text)
    chunks = []
    current = ""
    for para in paragraphs:
        # 단일 문단이 MAX_CHUNK_LEN을 초과하면 줄 단위로 자른다
        if len(para) > MAX_CHUNK_LEN:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_by_lines(para))
            continue
        if len(current) + len(para) + 2 > MAX_CHUNK_LEN and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


def _split_by_lines(text: str) -> list[str]:
    """줄 단위로 MAX_CHUNK_LEN 이하로 분할한다."""
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_CHUNK_LEN and current:
            chunks.append(current.strip())
            current = line
        else:
            current = current + "\n" + line if current else line
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


def chunk_document(doc: dict) -> list[dict]:
    """단일 문서를 청크 리스트로 변환한다.

    doc: {source, url, title, content}
    반환: [{source, url, header, content}]
    """
    content = doc["content"]
    source = doc["source"]
    url = doc["url"]

    # 1차: H1 기준 분리
    h1_parts = _split_by_pattern(content, H1_PATTERN)

    chunks = []
    for part in h1_parts:
        # 길이 초과 시 추가 분할
        sub_parts = _split_chunk(part)
        for sp in sub_parts:
            header = _extract_header(sp)
            chunks.append(
                {
                    "source": source,
                    "url": url,
                    "header": header,
                    "content": sp.strip(),
                }
            )

    return chunks


def chunk_all(collected: dict) -> list[dict]:
    """수집된 전체 문서를 청킹한다.

    collected: {source_key: {raw_text, documents: [...]}}
    반환: [{source, url, header, content}]
    """
    all_chunks = []
    for source_key, data in collected.items():
        for doc in data["documents"]:
            chunks = chunk_document(doc)
            all_chunks.extend(chunks)

    logger.info(
        "청킹 완료: 총 %d개 청크, 평균 %.0f자, 최대 %d자",
        len(all_chunks),
        sum(len(c["content"]) for c in all_chunks) / max(len(all_chunks), 1),
        max((len(c["content"]) for c in all_chunks), default=0),
    )
    return all_chunks
