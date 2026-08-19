# toss-mcp

> AI 코딩 에이전트에게 토스 개발자 문서, 기본 제공 아이콘, 공식 Apps in Toss 예제를 제공하는 MCP 서버

[토스 개발자 문서](https://developers-apps-in-toss.toss.im)(앱인토스, TDS React Native, TDS Mobile)의 **최신 내용**, 토스 기본 제공 아이콘, [공식 Apps in Toss 예제](https://github.com/toss/apps-in-toss-examples)를 AI가 검색할 수 있도록 제공하는 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 서버입니다.

## 주요 기능

- AI 에이전트가 토스 공식 문서를 바로 검색해 답변에 활용할 수 있습니다.
- 문서 검색 시 공식 문서군, 내장 배포 가이드, 현장 노트별 필터를 적용할 수 있습니다.
- 공식 문서에 없는 콘솔/담당자 확인 사항은 큐레이션된 `field_notes`로 검색되며, 앱인토스 관련 쿼리에는 함께 반환됩니다.
- `list_sources`로 실제 수집 중인 `llms.txt`/`llms-full.txt` 원천과 청크 수를 확인할 수 있습니다.
- 최신 문서가 필요할 때 `sync_sources`로 수동 동기화할 수 있습니다.
- 앱인토스 번들의 환경값 검증부터 CLI 업로드, 콘솔 검토·출시까지 범용 배포 체크리스트를 제공합니다.
- 토스 아이콘 카탈로그를 검색해 아이콘 이름/URL을 빠르게 찾을 수 있습니다.
- 아이콘 타입(`icon-*`, `icn-*`, `u1F...`)에 맞는 권장 컴포넌트 사용법을 바로 안내받을 수 있습니다.
- 실행할 때마다 공식 예제 저장소 `main`의 최신 commit을 확인하고, 변경된 경우 안전한 텍스트 파일만 선별해 캐시를 갱신합니다.
- 공식 예제를 예제명·플랫폼·언어·SDK 버전별로 찾고 원본 파일의 원하는 줄 범위를 조회할 수 있습니다.

## 빠른 시작

### 필수 조건

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (uvx 사용 시)

### 원격 실행 (uvx)

아래 클라이언트 설정은 모두 동일한 실행 정보를 사용합니다.
- `command`: `uvx`
- `args`: `["--refresh", "--from", "git+https://github.com/chabinhwang/toss-mcp@main", "toss-mcp"]`

`@main`과 `--refresh`를 함께 사용하므로 MCP를 실행할 때마다 최신 toss-mcp commit을 확인하고 자동으로 업데이트합니다. 재현 가능한 특정 릴리스를 고정하려면 `@main`을 `@v2.5.0`으로 바꾸고 `--refresh`를 제거하세요.

#### Claude Code

설정 파일: `~/.claude/settings.json` (`mcpServers`에 추가)

```json
{
  "toss-docs": {
    "command": "uvx",
    "args": ["--refresh", "--from", "git+https://github.com/chabinhwang/toss-mcp@main", "toss-mcp"]
  }
}
```

#### Codex

설정 파일: `~/.codex/config.toml` (`mcp_servers`에 추가)

```toml
[mcp_servers.toss-docs]
command = "uvx"
args = ["--refresh", "--from", "git+https://github.com/chabinhwang/toss-mcp@main", "toss-mcp"]
```

#### Gemini CLI

설정 파일: `~/.gemini/settings.json` (`mcpServers`에 추가)

```json
{
  "mcpServers": {
    "toss-docs": {
      "command": "uvx",
      "args": ["--refresh", "--from", "git+https://github.com/chabinhwang/toss-mcp@main", "toss-mcp"]
    }
  }
}
```
#### Claude Desktop

설정 파일:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

`mcpServers`에 아래를 추가:

```json
{
  "mcpServers": {
    "toss-docs": {
      "command": "uvx",
      "args": ["--refresh", "--from", "git+https://github.com/chabinhwang/toss-mcp@main", "toss-mcp"]
    }
  }
}
```

### 로컬 설치 (개발용)

```bash
git clone https://github.com/chabinhwang/toss-mcp.git
cd toss-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

설정 파일: MCP 클라이언트의 `mcpServers` 항목

```json
{
  "toss-docs": {
    "command": "/absolute/path/to/toss-mcp/.venv/bin/toss-mcp"
  }
}
```

## 제공 도구

### `search_docs`

토스 개발자 문서와 내장 보완 자료를 키워드로 검색합니다. 공식 send-message 스펙에 없는 이동 URL `{{ 변수 }}` 치환처럼 콘솔/담당자 확인 사항은 `field_notes`에 있습니다. `apps_in_toss`만 필터해도 관련 현장 노트는 함께 반환됩니다.

```
검색어: "앱인토스 결제 API"
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `query` | string | O | 검색어 (공백으로 구분된 키워드) |
| `source` | string | X | 소스 필터 (아래 표 참고) |
| `max_results` | number | X | 최대 결과 수 (기본 10, 최대 30) |

**소스 목록**

| 값 | 설명 |
|---|------|
| `apps_in_toss` | 앱인토스 |
| `tds_react_native` | TDS React Native |
| `tds_mobile` | TDS Mobile |
| `deployment_guide` | 범용 앱인토스 배포 실전 가이드(내장 보완 문서) |
| `field_notes` | 공식 문서에 없는 콘솔/담당자 확인 현장 노트(비공식, 커뮤니티 근거 포함) |

### `list_sources`

검색 가능한 소스, 공식 index/full 원천 URL, 수집 방식, 현재 검색 청크 수를 보여줍니다.

**현재 공식 원천**

| 문서군 | index | full | 검색 문서 구성 |
|---|---|---|---|
| 앱인토스 | `https://developers-apps-in-toss.toss.im/llms.txt` | `https://developers-apps-in-toss.toss.im/llms-full.txt` | index의 개별 Markdown 페이지를 수집하고, 불완전할 때 full로 폴백 |
| TDS React Native | `https://tossmini-docs.toss.im/tds-react-native/llms.txt` | `https://tossmini-docs.toss.im/tds-react-native/llms-full.txt` | full을 검색 대상으로 사용 |
| TDS Mobile | `https://tossmini-docs.toss.im/tds-mobile/llms.txt` | `https://tossmini-docs.toss.im/tds-mobile/llms-full.txt` | full을 검색 대상으로 사용 |

index와 full은 모두 변경 감지에 사용하지만, 같은 내용을 검색 결과에 중복 저장하지는 않습니다. 확인 결과 `tossmini-docs.toss.im` 도메인 루트와 `/tds-web/`에는 현재 별도 `llms.txt`/`llms-full.txt`가 없습니다.

별도 공식 개발 문서인 [토스페이먼츠 개발자센터](https://docs.tosspayments.com/llms.txt)도 확인했지만, 앱인토스/TDS와 다른 제품군이고 [전용 공식 MCP](https://docs.tosspayments.com/guides/v2/get-started/llms-guide)를 제공하므로 이 서버에는 합치지 않았습니다. 이 서버의 범위는 앱인토스 미니앱과 그 TDS 문서로 유지합니다. 공식 문서에 없는 콘솔/담당자 확인 사항은 `field_notes`로 큐레이션하며, 커뮤니티를 크롤하지 않습니다. 현재 send-message 이동 URL `{{ 변수 }}` 치환 노트의 근거는 [랜딩 URL 동적 파라미터](https://techchat-apps-in-toss.toss.im/t/url/3297), [발송 건별 동적 랜딩 URL](https://techchat-apps-in-toss.toss.im/t/send-message-api-url/4354)입니다.

### `sync_sources`

문서를 수동으로 동기화합니다. 최신 문서가 필요할 때 사용합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `force` | boolean | X | `true`이면 캐시 무시 후 강제 재수집 |

### `search_icons`

토스 아이콘 카탈로그(`toss_icons.json.gz`)를 검색하고, 아이콘 타입별 추천 사용 코드를 안내합니다.

```
검색어: "icon-search-bold-mono"
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `query` | string | O | 검색어 (아이콘 이름/URL 일부, 공백으로 구분된 키워드) |
| `icon_type` | string | X | 타입 필터 (`icon-*`, `icn-*`, `emoji/image`) |
| `max_results` | number | X | 최대 결과 수 (기본 10, 최대 30) |

**빠른 판단 규칙**

- 이름이 `icon-`/`icn-`면 `name` 기반 컴포넌트 (`Icon`, `IconButton`, `Asset.Icon`)
- 이름이 `u1F...`면 URL 기반 (`Asset.Image`, `Asset.ContentImage`)

### `list_examples`

검색 가능한 Apps in Toss 공식 예제와 SDK 버전을 보여줍니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `platform` | string | X | 플랫폼 필터 (`webview`, `react_native`, `server`) |

### `search_examples`

공식 예제의 README와 선별된 소스 코드를 검색합니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `query` | string | O | API, 함수, 기능 또는 코드 키워드 |
| `example` | string | X | 예제 ID 필터 (`list_examples`에서 확인) |
| `language` | string | X | `markdown`, `json`, `typescript`, `tsx`, `javascript`, `jsx` |
| `max_results` | number | X | 최대 결과 수 (기본 5, 최대 20) |

각 결과에는 원본 저장소 경로, 줄 번호, commit SHA, SDK 버전, Apache-2.0 라이선스가 표시됩니다.

### `get_example_file`

`search_examples`가 반환한 경로에서 원하는 줄 범위를 조회합니다. 한 번에 최대 400줄까지 반환합니다.

### `sync_examples`

공식 예제 저장소 `main`의 최신 commit을 수동 확인합니다. `force=true`이면 같은 commit도 다시 다운로드하고 라이선스와 파일을 재검증합니다.

## 기술적 특징

- 토스 개발자 공식 문서 3개 문서군·6개 index/full 원천 자동 추적
- ETag → Last-Modified → 본문 SHA256 순서의 변경 감지(ETag 없는 원천 지원)
- 앱인토스 개별 Markdown 페이지 수집 실패 시 루트 `llms-full.txt` 폴백
- 마크다운 헤더 기반 지능형 청킹 (H1 → H2 → H3 재귀 분할)
- 줄바꿈 없는 긴 HTML/table 행까지 청크 최대 3,000자 보장
- 2단계 키워드 검색 (정확 매칭 우선, 부분 매칭 폴백)
- 원천 validator 기반 변경 감지 + 로컬 캐시로 빠른 재시작
- 비동기 병렬 수집 (동시 8개 요청)
- 패키지 내장 범용 앱인토스 배포 실전 가이드
- 아이콘 카탈로그 압축 리소스(`toss_mcp/data/toss_icons.json.gz`) 로드 지원
- 공식 예제 GitHub API ETag + 최신 commit SHA 변경 감지
- Apache-2.0 검증 후 README·package manifest·소스 코드만 allowlist 수집
- 이미지·로고·환경 파일·인증서·lockfile·생성 파일 제외
- 함수·hook·컴포넌트와 줄 범위를 보존하는 코드 전용 청킹
- 검증 또는 네트워크 장애 시 마지막 정상 예제 스냅샷 유지

## 동작 방식

```
공식 index/full 원천 6개 변경 감지
       ↓
  앱인토스: index 링크의 개별 페이지 병렬 수집
  TDS 2종: full 문서 수집
       ↓ (개별 페이지 누락 시 앱인토스 full 폴백)
  마크다운 헤더 기반 청킹 (최대 3,000자)
       ↓
  공식 문서 로컬 캐시 (~/.toss-mcp-cache/)
       +
  패키지 내장 배포 가이드
       ↓
  소스 필터 가능한 키워드 검색

공식 예제 main commit 조건부 확인
       ↓ (SHA 변경 시)
  GitHub tarball 다운로드
       ↓
  Apache-2.0/NOTICE + 경로·크기 검증
       ↓
  allowlist 텍스트 선별 + 코드 청킹
       ↓
  원자적 예제 캐시 교체
```

- **캐시**: 시작 시 각 문서군의 index와 full 원천 validator를 비교하고, 변경이 없으면 캐시에서 로드합니다. ETag나 Last-Modified가 없으면 본문 SHA256을 비교합니다.
- **부분 장애**: 갱신 중 특정 문서군 수집에 실패하면 해당 문서군의 기존 캐시를 유지합니다.
- **내장 가이드**: 배포 가이드와 현장 노트는 패키지에서 매번 로드하므로 공식 문서 캐시에 섞이거나 오래된 캐시에 가려지지 않습니다. 현장 노트는 커뮤니티를 크롤하지 않고, 담당자 확인이 있는 항목만 큐레이션합니다.
- **재동기화**: `sync_sources(force=True)` 호출 또는 캐시 디렉토리 삭제 후 재시작하면 됩니다.
- **공식 예제 최신화**: 매 실행 시 최신 SHA를 확인합니다. 실패하거나 라이선스가 달라지면 새 스냅샷을 거부하고 마지막 정상 캐시를 유지합니다.
- **공식 예제 출처**: 검색 결과마다 commit 고정 원본 URL과 Apache-2.0 고지를 포함합니다.

## 공식 원천 실수집 검증

2026-08-10에 캐시 없는 상태로 공식 원천을 직접 수집하고 검색까지 확인한 결과입니다. 문서가 추가·삭제되면 개수는 달라질 수 있습니다.

| 소스 | 수집 문서 | 검색 청크 |
|---|---:|---:|
| `apps_in_toss` | 개별 Markdown 241개 | 1,480개 |
| `tds_react_native` | full 문서 1개 | 177개 |
| `tds_mobile` | full 문서 1개 | 370개 |
| `deployment_guide` | 내장 문서 1개 | 1개 |
| `field_notes` | 내장 노트 1개 | 1개 |

- 6개 index/full 원천이 모두 HTTP 200으로 응답하고 수집됐습니다.
- 연속으로 validator를 계산했을 때 6개 모두 같은 값으로 판정됐습니다.
- `ait deploy 검토 요청`, `미니앱 출시 롤백`, `IconButton` 검색을 각 대상 소스에서 확인했습니다.

## 프로젝트 구조

```
toss-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
└── toss_mcp/
    ├── __init__.py
    ├── main.py          # MCP 서버 엔트리포인트
    ├── collector.py     # 문서 수집 (httpx 비동기)
    ├── chunker.py       # 마크다운 청킹
    ├── searcher.py      # 키워드 검색
    ├── example_collector.py # GitHub 최신 SHA·라이선스·allowlist 수집
    ├── example_chunker.py   # Markdown/TS/TSX/JS 예제 청킹
    ├── example_searcher.py  # 예제 검색·카탈로그
    ├── examples.py      # 최신성 확인 + 스냅샷 구성
    ├── icons.py         # 아이콘 카탈로그 로드/검색 + 타입별 추천
    ├── knowledge.py     # 패키지 내장 보완 가이드 로드
    ├── cache.py         # JSON 캐시 + 해시 관리
    └── data/
        ├── toss_icons.json.gz
        ├── deployment_guide.md
        ├── field_notes/
        │   └── send-message-landing-url.md
        └── licenses/
            └── apps-in-toss-examples-APACHE-2.0.txt
```

## 라이선스

`toss-mcp` 자체 코드는 MIT License입니다.

런타임에 선별·캐시하는 [`toss/apps-in-toss-examples`](https://github.com/toss/apps-in-toss-examples)의 예제 자료는 Apache License 2.0이며, 해당 조건은 MIT로 대체되지 않습니다. 자세한 출처와 고지는 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)를 참고하세요.

이 프로젝트는 독립적인 오픈소스 프로젝트이며 Toss의 보증이나 제휴를 의미하지 않습니다.
