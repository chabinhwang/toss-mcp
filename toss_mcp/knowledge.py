"""공식 문서를 보완하는 범용 내장 가이드와 현장 노트."""

from __future__ import annotations

import logging
from importlib import resources
from typing import Any

logger = logging.getLogger(__name__)

FIELD_NOTES_SOURCE = "field_notes"

STATIC_SOURCES = {
    "deployment_guide": {
        "name": "앱인토스 배포 실전 가이드",
        "url": "toss-mcp://guides/apps-in-toss-deployment",
        "resource": "data/deployment_guide.md",
        "kind": "guide",
    },
    FIELD_NOTES_SOURCE: {
        "name": "앱인토스 현장 노트",
        "url": "toss-mcp://guides/field-notes",
        "resource": "data/field_notes",
        "kind": "field_notes",
        "description": (
            "공식 문서에 없는 콘솔/담당자 확인 사항. 비공식이며 "
            "개발자 커뮤니티 근거 링크를 포함한다."
        ),
    },
}

_PASSTHROUGH_META = (
    "triggers",
    "status",
    "related_sources",
    "citations",
    "as_of",
)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """문서 상단 YAML 프론트매터를 파싱한다. 실패하면 원문을 그대로 반환한다."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    closing = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = index
            break
    if closing is None:
        return {}, text

    meta = _parse_simple_yaml(lines[1:closing])
    body = "\n".join(lines[closing + 1 :]).lstrip("\n")
    return meta, body


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list_key is not None:
            item = _unquote(stripped[2:].strip())
            data.setdefault(current_list_key, []).append(item)
            continue

        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = _unquote(value.strip())
        if value == "":
            current_list_key = key
            data[key] = []
        else:
            current_list_key = None
            data[key] = value

    return data


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _note_id(meta: dict[str, Any], filename: str) -> str:
    note_id = str(meta.get("id") or "").strip()
    if note_id:
        return note_id
    return filename.removesuffix(".md")


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _document_from_markdown(
    source_key: str,
    source: dict[str, Any],
    filename: str,
    raw_text: str,
) -> dict[str, Any]:
    meta, body = parse_frontmatter(raw_text)
    note_id = _note_id(meta, filename)
    title = str(meta.get("title") or source["name"])
    document: dict[str, Any] = {
        "source": source_key,
        "url": f"{source['url'].rstrip('/')}/{note_id}"
        if source.get("kind") == "field_notes"
        else source["url"],
        "title": title,
        "content": body or raw_text,
    }

    for key in _PASSTHROUGH_META:
        values = meta.get(key)
        if key in {"triggers", "related_sources", "citations"}:
            document[key] = _as_list(values)
        elif values:
            document[key] = values

    return document


def _load_static_documents(
    source_key: str,
    source: dict[str, Any],
    resource,
) -> list[dict[str, Any]]:
    try:
        if resource.is_dir():
            files = sorted(
                (
                    item
                    for item in resource.iterdir()
                    if item.name.endswith(".md") and not item.name.startswith(".")
                ),
                key=lambda item: item.name,
            )
            documents = []
            for item in files:
                documents.append(
                    _document_from_markdown(
                        source_key,
                        source,
                        item.name,
                        item.read_text("utf-8"),
                    )
                )
            return documents

        content = resource.read_text("utf-8")
    except (FileNotFoundError, OSError) as exc:
        logger.error("내장 가이드 로드 실패: %s → %s", source_key, exc)
        return []

    return [
        {
            "source": source_key,
            "url": source["url"],
            "title": source["name"],
            "content": content,
        }
    ]


def collect_static_sources() -> dict:
    """패키지에 포함된 범용 가이드를 공식 문서와 같은 형태로 반환한다."""
    collected: dict = {}
    package_root = resources.files("toss_mcp")

    for source_key, source in STATIC_SOURCES.items():
        resource = package_root.joinpath(source["resource"])
        documents = _load_static_documents(source_key, source, resource)
        if not documents:
            continue

        collected[source_key] = {
            "raw_text": "\n\n".join(doc["content"] for doc in documents),
            "documents": documents,
        }

    return collected
