# toss-mcp

> AI 코딩 에이전트에게 토스 개발자 문서 및 토스 기본 제공 아이콘 정보를 제공하는 MCP 서버

[토스 개발자 문서](https://developers-apps-in-toss.toss.im)(앱인토스, TDS React Native, TDS Mobile)에 대한 **최신 내용**  및 토스에서 제공하는 아이콘 들에 대한 정보를 AI가 검색할 수 있도록 제공하는 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 서버입니다.

## 주요 기능

- AI 에이전트가 토스 공식 문서를 바로 검색해 답변에 활용할 수 있습니다.
- 문서 검색 시 공식 문서군 또는 내장 배포 가이드별 필터를 적용할 수 있습니다.
- `list_sources`로 실제 수집 중인 `llms.txt`/`llms-full.txt` 원천과 청크 수를 확인할 수 있습니다.
- 최신 문서가 필요할 때 `sync_sources`로 수동 동기화할 수 있습니다.
- 앱인토스 번들의 환경값 검증부터 CLI 업로드, 콘솔 검토·출시까지 범용 배포 체크리스트를 제공합니다.
- 토스 아이콘 카탈로그를 검색해 아이콘 이름/URL을 빠르게 찾을 수 있습니다.
- 아이콘 타입(`icon-*`, `icn-*`, `u1F...`)에 맞는 권장 컴포넌트 사용법을 바로 안내받을 수 있습니다.

## 빠른 시작

### 필수 조건

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (uvx 사용 시)

### 원격 실행 (uvx)

아래 클라이언트 설정은 모두 동일한 실행 정보를 사용합니다.
- `command`: `uvx`
- `args`: `["--from", "git+https://github.com/chabinhwang/toss-mcp@v2.3.0", "toss-mcp"]`

#### Claude Code

설정 파일: `~/.claude/settings.json` (`mcpServers`에 추가)

```json
{
  "toss-docs": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp@v2.3.0", "toss-mcp"]
  }
}
```

#### Codex

설정 파일: `~/.codex/config.toml` (`mcp_servers`에 추가)

```toml
[mcp_servers.toss-docs]
command = "uvx"
args = ["--from", "git+https://github.com/chabinhwang/toss-mcp@v2.3.0", "toss-mcp"]
```

#### Gemini CLI

설정 파일: `~/.gemini/settings.json` (`mcpServers`에 추가)

```json
{
  "mcpServers": {
    "toss-docs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp@v2.3.0", "toss-mcp"]
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
      "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp@v2.3.0", "toss-mcp"]
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

토스 개발자 문서를 키워드로 검색합니다.

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

### `list_sources`

검색 가능한 소스, 공식 index/full 원천 URL, 수집 방식, 현재 검색 청크 수를 보여줍니다.

**현재 공식 원천**

| 문서군 | index | full | 검색 문서 구성 |
|---|---|---|---|
| 앱인토스 | `https://developers-apps-in-toss.toss.im/llms.txt` | `https://developers-apps-in-toss.toss.im/llms-full.txt` | index의 개별 Markdown 페이지를 수집하고, 불완전할 때 full로 폴백 |
| TDS React Native | `https://tossmini-docs.toss.im/tds-react-native/llms.txt` | `https://tossmini-docs.toss.im/tds-react-native/llms-full.txt` | full을 검색 대상으로 사용 |
| TDS Mobile | `https://tossmini-docs.toss.im/tds-mobile/llms.txt` | `https://tossmini-docs.toss.im/tds-mobile/llms-full.txt` | full을 검색 대상으로 사용 |

index와 full은 모두 변경 감지에 사용하지만, 같은 내용을 검색 결과에 중복 저장하지는 않습니다. 확인 결과 `tossmini-docs.toss.im` 도메인 루트와 `/tds-web/`에는 현재 별도 `llms.txt`/`llms-full.txt`가 없습니다.

별도 공식 개발 문서인 [토스페이먼츠 개발자센터](https://docs.tosspayments.com/llms.txt)도 확인했지만, 앱인토스/TDS와 다른 제품군이고 [전용 공식 MCP](https://docs.tosspayments.com/guides/v2/get-started/llms-guide)를 제공하므로 이 서버에는 합치지 않았습니다. 이 서버의 범위는 앱인토스 미니앱과 그 TDS 문서로 유지합니다.

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
```

- **캐시**: 시작 시 각 문서군의 index와 full 원천 validator를 비교하고, 변경이 없으면 캐시에서 로드합니다. ETag나 Last-Modified가 없으면 본문 SHA256을 비교합니다.
- **부분 장애**: 갱신 중 특정 문서군 수집에 실패하면 해당 문서군의 기존 캐시를 유지합니다.
- **내장 가이드**: 배포 가이드는 패키지에서 매번 로드하므로 공식 문서 캐시에 섞이거나 오래된 캐시에 가려지지 않습니다.
- **재동기화**: `sync_sources(force=True)` 호출 또는 캐시 디렉토리 삭제 후 재시작하면 됩니다.

## 공식 원천 실수집 검증

2026-08-10에 캐시 없는 상태로 공식 원천을 직접 수집하고 검색까지 확인한 결과입니다. 문서가 추가·삭제되면 개수는 달라질 수 있습니다.

| 소스 | 수집 문서 | 검색 청크 |
|---|---:|---:|
| `apps_in_toss` | 개별 Markdown 241개 | 1,480개 |
| `tds_react_native` | full 문서 1개 | 177개 |
| `tds_mobile` | full 문서 1개 | 370개 |
| `deployment_guide` | 내장 문서 1개 | 1개 |

- 6개 index/full 원천이 모두 HTTP 200으로 응답하고 수집됐습니다.
- 연속으로 validator를 계산했을 때 6개 모두 같은 값으로 판정됐습니다.
- `ait deploy 검토 요청`, `미니앱 출시 롤백`, `IconButton` 검색을 각 대상 소스에서 확인했습니다.

## 프로젝트 구조

```
toss-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
└── toss_mcp/
    ├── __init__.py
    ├── main.py          # MCP 서버 엔트리포인트
    ├── collector.py     # 문서 수집 (httpx 비동기)
    ├── chunker.py       # 마크다운 청킹
    ├── searcher.py      # 키워드 검색
    ├── icons.py         # 아이콘 카탈로그 로드/검색 + 타입별 추천
    ├── knowledge.py     # 패키지 내장 보완 가이드 로드
    ├── cache.py         # JSON 캐시 + 해시 관리
    └── data/
        ├── toss_icons.json.gz
        └── deployment_guide.md
```

## 라이선스

MIT License
