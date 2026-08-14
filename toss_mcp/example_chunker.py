"""공식 예제 Markdown과 소스 코드를 검색 가능한 청크로 분리한다."""

from __future__ import annotations

import re

from .chunker import MAX_CHUNK_LEN, chunk_document

DECLARATION_PATTERN = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*))",
)


def _line_windows(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        size = 0
        stop = cursor
        while stop < end:
            addition = len(lines[stop]) + 1
            if stop > cursor and size + addition > MAX_CHUNK_LEN:
                break
            size += addition
            stop += 1
        windows.append((cursor, max(stop, cursor + 1)))
        cursor = max(stop, cursor + 1)
    return windows


def _code_ranges(lines: list[str]) -> list[tuple[int, int, str]]:
    declarations: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = DECLARATION_PATTERN.match(line)
        if match:
            declarations.append((index, match.group(1) or match.group(2) or ""))

    boundaries = sorted({0, *(index for index, _ in declarations), len(lines)})
    symbols = {index: symbol for index, symbol in declarations}
    ranges: list[tuple[int, int, str]] = []
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        if start == end:
            continue
        symbol = symbols.get(start, "imports/config" if start == 0 else "")
        for window_start, window_end in _line_windows(lines, start, end):
            ranges.append((window_start, window_end, symbol))
    return ranges


def _base_chunk(file: dict, commit: str) -> dict:
    return {
        "source": "official_examples",
        "example": file["example"],
        "path": file["path"],
        "language": file["language"],
        "url": file["url"],
        "commit": commit,
        "license": "Apache-2.0",
        "sdk_packages": file.get("sdk_packages", {}),
    }


def _markdown_chunks(file: dict, commit: str) -> list[dict]:
    chunks = chunk_document(
        {
            "source": "official_examples",
            "url": file["url"],
            "title": file["path"],
            "content": file["content"],
        }
    )
    result = []
    cursor = 0
    for chunk in chunks:
        content = chunk["content"]
        position = file["content"].find(content, cursor)
        if position < 0:
            position = file["content"].find(content)
        start_line = file["content"].count("\n", 0, max(position, 0)) + 1
        end_line = start_line + content.count("\n")
        result.append(
            {
                **_base_chunk(file, commit),
                "header": chunk["header"] or file["path"],
                "content": content,
                "start_line": start_line,
                "end_line": end_line,
            }
        )
        cursor = max(position, 0) + len(content)
    return result


def _code_chunks(file: dict, commit: str) -> list[dict]:
    lines = file["content"].splitlines()
    if not lines:
        return []
    result = []
    for start, end, symbol in _code_ranges(lines):
        content = "\n".join(lines[start:end]).strip()
        if not content:
            continue
        result.append(
            {
                **_base_chunk(file, commit),
                "header": symbol or file["path"],
                "content": content,
                "start_line": start + 1,
                "end_line": end,
            }
        )
    return result


def chunk_example_files(files: list[dict], commit: str) -> list[dict]:
    """선별 파일을 출처·줄 번호가 보존된 청크로 만든다."""
    chunks: list[dict] = []
    for file in files:
        if file["language"] == "markdown":
            chunks.extend(_markdown_chunks(file, commit))
        else:
            chunks.extend(_code_chunks(file, commit))
    return chunks
