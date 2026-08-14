"""공식 예제 전용 검색과 카탈로그 구성."""

from __future__ import annotations

import re


def search_examples(
    chunks: list[dict],
    query: str,
    example: str | None = None,
    language: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    keywords = query.lower().split()
    if not keywords:
        return []

    results: list[tuple[int, dict]] = []
    for chunk in chunks:
        if example and chunk["example"] != example:
            continue
        if language and chunk["language"] != language:
            continue

        path = chunk["path"].lower()
        header = chunk["header"].lower()
        content = chunk["content"].lower()
        sdk_text = " ".join(
            f"{name} {version}" for name, version in chunk["sdk_packages"].items()
        ).lower()
        searchable = f"{chunk['example']} {path} {header} {sdk_text} {content}"
        matched = [keyword for keyword in keywords if keyword in searchable]
        if not matched:
            continue

        score = len(matched) * 10
        score += sum(8 for keyword in keywords if keyword in header)
        score += sum(5 for keyword in keywords if keyword in path)
        score += sum(3 for keyword in keywords if keyword in sdk_text)
        if query.lower() in header:
            score += 15
        if len(matched) == len(keywords):
            score += 20
        if chunk["language"] != "markdown":
            score += 6
        results.append(
            (
                score,
                {
                    **chunk,
                    "match_count": len(matched),
                    "match_ratio": len(matched) / len(keywords),
                    "score": score,
                },
            )
        )

    results.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["start_line"]))
    return [item for _, item in results[:max_results]]


def _readme_title(content: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _readme_summary(content: str) -> str:
    paragraphs = re.split(r"\n\s*\n", content)
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped or stripped.startswith(("#", "![", "<img")):
            continue
        return " ".join(stripped.split())[:300]
    return ""


def list_example_summaries(files: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for file in files:
        if file["example"] == "repository":
            continue
        grouped.setdefault(file["example"], []).append(file)

    summaries = []
    for example, example_files in sorted(grouped.items()):
        readme = next(
            (file for file in example_files if file["path"] == f"{example}/README.md"),
            next(
                (file for file in example_files if file["path"].endswith("/README.md")),
                None,
            ),
        )
        sdk_packages: dict[str, str] = {}
        languages = set()
        platforms = set()
        for file in example_files:
            sdk_packages.update(file.get("sdk_packages", {}))
            languages.add(file["language"])
            packages = file.get("sdk_packages", {})
            if "@apps-in-toss/web-framework" in packages:
                platforms.add("webview")
            if "@apps-in-toss/framework" in packages:
                platforms.add("react_native")
            if "/server/" in f"/{file['path']}":
                platforms.add("server")
        summaries.append(
            {
                "example": example,
                "title": (
                    _readme_title(readme["content"], example) if readme else example
                ),
                "summary": _readme_summary(readme["content"]) if readme else "",
                "file_count": len(example_files),
                "languages": sorted(languages),
                "platforms": sorted(platforms),
                "sdk_packages": dict(sorted(sdk_packages.items())),
            }
        )
    return summaries
