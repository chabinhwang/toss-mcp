"""공식 문서를 보완하는 범용 내장 가이드."""

import logging
from importlib import resources

logger = logging.getLogger(__name__)

STATIC_SOURCES = {
    "deployment_guide": {
        "name": "앱인토스 배포 실전 가이드",
        "url": "toss-mcp://guides/apps-in-toss-deployment",
        "resource": "data/deployment_guide.md",
    }
}


def collect_static_sources() -> dict:
    """패키지에 포함된 범용 가이드를 공식 문서와 같은 형태로 반환한다."""
    collected: dict = {}
    package_root = resources.files("toss_mcp")

    for source_key, source in STATIC_SOURCES.items():
        resource = package_root.joinpath(source["resource"])
        try:
            content = resource.read_text("utf-8")
        except (FileNotFoundError, OSError) as exc:
            logger.error("내장 가이드 로드 실패: %s → %s", source_key, exc)
            continue

        collected[source_key] = {
            "raw_text": content,
            "documents": [
                {
                    "source": source_key,
                    "url": source["url"],
                    "title": source["name"],
                    "content": content,
                }
            ],
        }

    return collected
