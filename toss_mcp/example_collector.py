"""공식 Apps in Toss 예제 저장소의 최신 선별 스냅샷 수집기."""

from __future__ import annotations

import io
import json
import os
import re
import tarfile
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

REPOSITORY = "toss/apps-in-toss-examples"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
DEFAULT_REF = "main"
LATEST_COMMIT_URL = f"https://api.github.com/repos/{REPOSITORY}/commits/{DEFAULT_REF}"
ARCHIVE_URL = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{{commit}}"
TIMEOUT = 30
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_SELECTED_FILE_BYTES = 512 * 1024
MAX_SELECTED_TOTAL_BYTES = 2 * 1024 * 1024

APACHE_LICENSE_MARKERS = (
    "Apache License",
    "Version 2.0, January 2004",
    "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION",
)
CODE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
CONFIG_FILES = {
    "apps-in-toss.config.ts",
    "granite.config.ts",
    "vite.config.ts",
    "server.js",
    "env.config.js",
    "index.ts",
}
EXCLUDED_PARTS = {
    ".git",
    ".yarn",
    "assets",
    "cert",
    "node_modules",
    "public",
}
EXCLUDED_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}
SDK_PACKAGE_PREFIXES = ("@apps-in-toss/", "@granite-js/")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ExampleSourceError(RuntimeError):
    """공식 예제 원천이 안전성 또는 라이선스 검증을 통과하지 못함."""


def is_selected_example_path(path: str) -> bool:
    """검색 가치가 있는 텍스트 파일만 허용한다."""
    normalized = PurePosixPath(path)
    parts = normalized.parts
    name = normalized.name

    if normalized.is_absolute() or ".." in parts:
        return False
    if any(part in EXCLUDED_PARTS for part in parts):
        return False
    if any(part.startswith(".env") for part in parts):
        return False
    if name in EXCLUDED_NAMES or name.endswith((".lock", ".key", ".crt")):
        return False
    if name == "vite-env.d.ts" or ".gen." in name:
        return False
    if name in {"README.md", "package.json"}:
        return True
    if name in CONFIG_FILES:
        return True
    if normalized.suffix not in CODE_SUFFIXES:
        return False
    return "src" in parts or "pages" in parts


def validate_apache_license(text: str) -> None:
    """원천이 Apache-2.0 원문을 포함하는지 보수적으로 확인한다."""
    if not all(marker in text for marker in APACHE_LICENSE_MARKERS):
        raise ExampleSourceError(
            "공식 예제 저장소의 LICENSE가 Apache-2.0으로 확인되지 않습니다."
        )


def _relative_archive_path(member_name: str) -> PurePosixPath:
    path = PurePosixPath(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise ExampleSourceError(f"안전하지 않은 아카이브 경로: {member_name}")
    if len(path.parts) > 1 and path.parts[0].startswith("apps-in-toss-examples-"):
        return PurePosixPath(*path.parts[1:])
    return path


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    if member.size > MAX_SELECTED_FILE_BYTES:
        raise ExampleSourceError(f"허용 크기를 넘는 예제 파일: {member.name}")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ExampleSourceError(f"예제 파일을 읽지 못했습니다: {member.name}")
    try:
        return extracted.read().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExampleSourceError(
            f"UTF-8 텍스트가 아닌 예제 파일: {member.name}"
        ) from exc


def _language_for(path: str) -> str:
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix
    if name == "README.md":
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix == ".tsx":
        return "tsx"
    if suffix == ".ts":
        return "typescript"
    if suffix == ".jsx":
        return "jsx"
    return "javascript"


def _example_id(path: str) -> str:
    parts = PurePosixPath(path).parts
    if not parts or len(parts) == 1:
        return "repository"
    if parts[0] == "user-identification" and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0]


def _package_manifests(files: dict[str, str]) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for path, content in files.items():
        if PurePosixPath(path).name != "package.json":
            continue
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExampleSourceError(f"잘못된 package.json: {path}") from exc
        if isinstance(parsed, dict):
            parent = PurePosixPath(path).parent.as_posix()
            manifests[parent] = parsed
    return manifests


def _nearest_manifest(path: str, manifests: dict[str, dict]) -> dict:
    parent = PurePosixPath(path).parent
    candidates = [
        (PurePosixPath(directory), manifest)
        for directory, manifest in manifests.items()
        if directory == "."
        or parent == PurePosixPath(directory)
        or PurePosixPath(directory) in parent.parents
    ]
    if not candidates:
        return {}
    return max(candidates, key=lambda item: len(item[0].parts))[1]


def _sdk_packages(manifest: dict) -> dict[str, str]:
    packages: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        values = manifest.get(section, {})
        if not isinstance(values, dict):
            continue
        for name, version in values.items():
            if name.startswith(SDK_PACKAGE_PREFIXES) and isinstance(version, str):
                packages[name] = version
    return dict(sorted(packages.items()))


def parse_example_archive(archive_bytes: bytes, commit: str) -> dict:
    """GitHub tarball을 검증하고 allowlist에 해당하는 파일만 반환한다."""
    if not SHA_PATTERN.fullmatch(commit):
        raise ExampleSourceError("예제 원천 commit SHA 형식이 올바르지 않습니다.")
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ExampleSourceError("공식 예제 아카이브가 허용 크기를 초과했습니다.")

    selected: dict[str, str] = {}
    license_text: str | None = None
    notice_text: str | None = None
    selected_size = 0

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = _relative_archive_path(member.name)
                if not member.isfile():
                    continue
                relative_path = relative.as_posix()
                if relative_path == "LICENSE":
                    license_text = _read_member(archive, member)
                    continue
                if relative_path in {"NOTICE", "NOTICE.txt"}:
                    notice_text = _read_member(archive, member)
                    continue
                if not is_selected_example_path(relative_path):
                    continue
                selected_size += member.size
                if selected_size > MAX_SELECTED_TOTAL_BYTES:
                    raise ExampleSourceError(
                        "선별된 공식 예제 파일이 허용 총 크기를 초과했습니다."
                    )
                selected[relative_path] = _read_member(archive, member)
    except tarfile.TarError as exc:
        raise ExampleSourceError("공식 예제 아카이브를 열지 못했습니다.") from exc

    if license_text is None:
        raise ExampleSourceError("공식 예제 저장소에 LICENSE가 없습니다.")
    validate_apache_license(license_text)
    if not selected:
        raise ExampleSourceError("검색 가능한 공식 예제 파일이 없습니다.")

    manifests = _package_manifests(selected)
    files = []
    for path, content in sorted(selected.items()):
        manifest = _nearest_manifest(path, manifests)
        files.append(
            {
                "path": path,
                "content": content,
                "example": _example_id(path),
                "language": _language_for(path),
                "url": f"{REPOSITORY_URL}/blob/{commit}/{quote(path, safe='/')}",
                "sdk_packages": _sdk_packages(manifest),
            }
        )

    return {
        "files": files,
        "license": "Apache-2.0",
        "notice": notice_text,
    }


def _github_headers(etag: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "toss-mcp",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if etag:
        headers["If-None-Match"] = etag
    return headers


async def fetch_latest_commit(
    client: httpx.AsyncClient,
    etag: str | None = None,
) -> dict:
    """main 최신 SHA를 조건부 요청으로 확인한다."""
    try:
        response = await client.get(
            LATEST_COMMIT_URL,
            headers=_github_headers(etag),
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if response.status_code == 304:
            return {"not_modified": True, "sha": None, "etag": etag}
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ExampleSourceError(
                "GitHub 최신 commit 응답 형식이 올바르지 않습니다."
            )
        sha = payload.get("sha")
        if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
            raise ExampleSourceError("GitHub 최신 commit 응답에 유효한 SHA가 없습니다.")
        return {
            "not_modified": False,
            "sha": sha,
            "etag": response.headers.get("etag"),
        }
    except (httpx.HTTPError, ValueError) as exc:
        raise ExampleSourceError(f"공식 예제 최신 commit 확인 실패: {exc}") from exc


async def fetch_example_archive(client: httpx.AsyncClient, commit: str) -> bytes:
    """검증할 특정 commit의 GitHub tarball을 받는다."""
    if not SHA_PATTERN.fullmatch(commit):
        raise ExampleSourceError("예제 원천 commit SHA 형식이 올바르지 않습니다.")
    try:
        response = await client.get(
            ARCHIVE_URL.format(commit=commit),
            headers={"User-Agent": "toss-mcp"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExampleSourceError(f"공식 예제 아카이브 수집 실패: {exc}") from exc
    if len(response.content) > MAX_ARCHIVE_BYTES:
        raise ExampleSourceError("공식 예제 아카이브가 허용 크기를 초과했습니다.")
    return response.content
