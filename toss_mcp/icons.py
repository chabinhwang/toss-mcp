"""토스 아이콘 카탈로그 로드 및 검색."""

import gzip
import json
import logging
from importlib import resources

logger = logging.getLogger(__name__)

MAX_ICON_RESULTS = 10
SUPPORTED_ICON_TYPES = ("icon-*", "icn-*", "emoji/image")

ICON_USAGE_GUIDE = """## 타입별 추천 코드
### 1) `icon-*` (시스템 아이콘, 특히 `-mono`는 색 변경용)
```tsx
import { Icon, IconButton } from '@toss/tds-react-native';

<Icon name="icon-trophy-mono" size={24} color="#8B95A1" />
<IconButton name="icon-search-bold-mono" />
```
- `-mono` 아이콘일 때 `color` 적용 권장

### 2) `icn-*` (브랜드/컬러 아이콘 계열)
```tsx
import { Icon, Asset } from '@toss/tds-react-native';

<Icon name="icn-bank-toss" size={24} />
<Asset.Icon name="icn-info-line" frameShape={Asset.frameShape.CleanH24} />
```
- 보통 원본 컬러를 쓰고 `color`는 제한적으로만 적용

### 3) `u1F...` (2D 이모지/이미지 리소스)
```tsx
import { Asset } from '@toss/tds-react-native';

<Asset.Image source={{ uri: 'https://static.toss.im/2d-emojis/svg/u1F68C-blue.svg' }} />
```
- 이 계열은 `name`보다 `source={{ uri }}`로 사용하는 게 안전함

## 빠른 판단 규칙
- 이름이 `icon-`/`icn-`면 `name` 기반 컴포넌트 (`Icon`, `IconButton`, `Asset.Icon`)
- 이름이 `u1F...`면 URL 기반 (`Asset.Image`, `Asset.ContentImage`)
"""


def _load_icon_payload_text() -> str | None:
    """패키지 리소스에서 아이콘 JSON 텍스트를 로드한다.

    우선순위:
    1) toss_mcp/data/toss_icons.json.gz
    2) toss_mcp/data/toss_icons.json
    """
    data_dir = resources.files("toss_mcp").joinpath("data")

    compressed = data_dir.joinpath("toss_icons.json.gz")
    if compressed.is_file():
        try:
            compressed_bytes = compressed.read_bytes()
            return gzip.decompress(compressed_bytes).decode("utf-8")
        except Exception as exc:
            logger.error("압축 아이콘 카탈로그 로드 실패: %s", exc)

    plain = data_dir.joinpath("toss_icons.json")
    if plain.is_file():
        try:
            return plain.read_text("utf-8")
        except Exception as exc:
            logger.error("일반 아이콘 카탈로그 로드 실패: %s", exc)

    logger.error(
        "아이콘 카탈로그 파일을 찾을 수 없습니다: "
        "toss_mcp/data/toss_icons.json(.gz)"
    )
    return None


def load_icon_items() -> list[dict]:
    """패키지 내 toss_icons.json에서 아이콘 목록을 로드한다."""
    raw = _load_icon_payload_text()
    if raw is None:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("아이콘 카탈로그 JSON 파싱 실패: %s", exc)
        return []

    items = payload.get("items")
    if not isinstance(items, list):
        logger.error("아이콘 카탈로그 형식 오류: 'items' 필드가 list가 아닙니다")
        return []
    return items


def _infer_usage_family(name: str, icon_type: str, src: str) -> str:
    """아이콘 이름/타입 기반으로 권장 사용 패밀리를 판별한다."""
    lower_name = name.lower()
    lower_type = icon_type.lower()
    lower_src = src.lower()

    if lower_name.startswith("icon-"):
        return "icon-*"
    if lower_name.startswith("icn-"):
        return "icn-*"
    if lower_name.startswith("u1f"):
        return "u1f"

    if lower_type == "icon-*":
        return "icon-*"
    if lower_type == "icn-*":
        return "icn-*"
    if lower_type == "emoji/image" or "2d-emojis" in lower_src:
        return "u1f"
    return "unknown"


def get_item_usage_hint(item: dict) -> str:
    """단일 아이콘에 대한 짧은 사용 가이드를 반환한다."""
    name = str(item.get("name", ""))
    icon_type = str(item.get("type", ""))
    src = str(item.get("src", ""))
    family = _infer_usage_family(name, icon_type, src)

    if family == "icon-*":
        if "-mono" in name.lower():
            return "name 기반 `Icon`/`IconButton` 사용 + `color` 적용 권장 (`-mono`)"
        return "name 기반 `Icon`/`IconButton` 사용 권장 (`icon-*`)"
    if family == "icn-*":
        return "name 기반 `Icon`/`Asset.Icon` 사용 권장 (`icn-*`, 원본 컬러 우선)"
    if family == "u1f":
        return "URL 기반 `Asset.Image`/`Asset.ContentImage` 사용 권장 (`source={{ uri }}`)"
    if src.startswith("http"):
        return "타입 판별이 불명확해 URL 기반 렌더링을 우선 권장"
    return "타입 판별이 불명확해 카탈로그 원본(`src`) 확인 권장"


def search_icon_catalog(
    items: list[dict],
    query: str,
    icon_type: str | None = None,
    max_results: int = MAX_ICON_RESULTS,
) -> list[dict]:
    """아이콘 카탈로그를 키워드로 검색한다."""
    keywords = [kw for kw in query.lower().split() if kw]
    if not keywords:
        return []

    normalized_type = icon_type.lower() if icon_type else None
    exact_matches: list[dict] = []
    partial_matches: list[dict] = []

    for item in items:
        name = str(item.get("name", ""))
        item_type = str(item.get("type", ""))
        src = str(item.get("src", ""))

        if normalized_type and item_type.lower() != normalized_type:
            continue

        searchable = f"{name} {item_type} {src}".lower()
        matched_keywords = [kw for kw in keywords if kw in searchable]
        match_count = len(matched_keywords)
        if match_count == 0:
            continue

        entry = {
            "name": name,
            "type": item_type,
            "src": src,
            "match_count": match_count,
            "match_ratio": match_count / len(keywords),
        }

        if match_count == len(keywords):
            exact_matches.append(entry)
        else:
            partial_matches.append(entry)

    sort_key = lambda x: (-x["match_count"], x["name"])
    exact_matches.sort(key=sort_key)
    partial_matches.sort(key=sort_key)
    return (exact_matches + partial_matches)[:max_results]
