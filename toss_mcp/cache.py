"""JSON 캐시 + SHA256 해시 변경 감지"""

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".toss-mcp-cache"
CHUNKS_FILE = CACHE_DIR / "chunks.json"
HASHES_FILE = CACHE_DIR / "hashes.json"
ETAGS_FILE = CACHE_DIR / "etags.json"
EXAMPLES_FILE = CACHE_DIR / "examples.json"


def _ensure_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def compute_hash(text: str) -> str:
    """텍스트의 SHA256 해시를 계산한다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_hashes() -> dict[str, str]:
    """저장된 해시를 로드한다."""
    _ensure_dir()
    if HASHES_FILE.exists():
        return json.loads(HASHES_FILE.read_text("utf-8"))
    return {}


def save_hashes(hashes: dict[str, str]):
    """해시를 저장한다."""
    _ensure_dir()
    HASHES_FILE.write_text(json.dumps(hashes, ensure_ascii=False), "utf-8")


def load_chunks() -> list[dict] | None:
    """캐시된 청크를 로드한다. 없으면 None."""
    _ensure_dir()
    if CHUNKS_FILE.exists():
        data = json.loads(CHUNKS_FILE.read_text("utf-8"))
        logger.info("캐시 로드: %d개 청크", len(data))
        return data
    return None


def save_chunks(chunks: list[dict]):
    """청크를 캐시에 저장한다."""
    _ensure_dir()
    CHUNKS_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=None), "utf-8")
    logger.info("캐시 저장: %d개 청크", len(chunks))


def needs_refresh(current_raw_texts: dict[str, str]) -> bool:
    """현재 원본 텍스트 해시와 저장된 해시를 비교하여 갱신 필요 여부를 반환한다."""
    saved = load_hashes()
    for key, text in current_raw_texts.items():
        current_hash = compute_hash(text)
        if saved.get(key) != current_hash:
            logger.info("해시 불일치: %s → 재수집 필요", key)
            return True
    # 캐시 파일이 없는 경우도 갱신 필요
    if not CHUNKS_FILE.exists():
        return True
    logger.info("해시 일치: 캐시 사용")
    return False


def update_hashes(raw_texts: dict[str, str]):
    """현재 원본 텍스트의 해시를 저장한다."""
    hashes = {key: compute_hash(text) for key, text in raw_texts.items()}
    save_hashes(hashes)


def load_etags() -> dict[str, str]:
    """저장된 ETag를 로드한다."""
    _ensure_dir()
    if ETAGS_FILE.exists():
        return json.loads(ETAGS_FILE.read_text("utf-8"))
    return {}


def save_etags(etags: dict[str, str]):
    """ETag를 저장한다."""
    _ensure_dir()
    ETAGS_FILE.write_text(json.dumps(etags, ensure_ascii=False), "utf-8")


def load_example_snapshot() -> dict | None:
    """마지막으로 검증에 성공한 공식 예제 스냅샷을 로드한다."""
    _ensure_dir()
    if not EXAMPLES_FILE.exists():
        return None
    try:
        snapshot = json.loads(EXAMPLES_FILE.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("공식 예제 캐시 로드 실패: %s", exc)
        return None
    if not isinstance(snapshot, dict):
        return None
    if not all(key in snapshot for key in ("manifest", "files", "chunks")):
        return None
    return snapshot


def save_example_snapshot(snapshot: dict) -> None:
    """검증 완료된 예제 스냅샷을 단일 파일로 원자적으로 교체한다."""
    _ensure_dir()
    temporary = EXAMPLES_FILE.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        "utf-8",
    )
    temporary.replace(EXAMPLES_FILE)
    logger.info(
        "공식 예제 캐시 저장: %d개 파일, %d개 청크",
        len(snapshot.get("files", [])),
        len(snapshot.get("chunks", [])),
    )
