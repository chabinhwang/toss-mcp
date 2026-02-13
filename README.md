# toss-mcp

> AI 코딩 에이전트에게 토스 개발자 문서를 제공하는 MCP 서버

[토스 개발자 문서](https://developers-apps-in-toss.toss.im)(앱인토스, TDS React Native, TDS Mobile)에 대한 **최신 내용** 을 자동으로 수집하고, AI가 검색할 수 있도록 제공하는 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 서버입니다.

## 주요 기능

- AI 에이전트가 토스 공식 문서를 바로 검색해 답변에 활용할 수 있습니다.
- 문서 검색 시 소스별 필터(`apps_in_toss`, `tds_react_native`, `tds_mobile`)를 적용할 수 있습니다.
- 최신 문서가 필요할 때 `sync_sources`로 수동 동기화할 수 있습니다.
- 토스 아이콘 카탈로그를 검색해 아이콘 이름/URL을 빠르게 찾을 수 있습니다.
- 아이콘 타입(`icon-*`, `icn-*`, `u1F...`)에 맞는 권장 컴포넌트 사용법을 바로 안내받을 수 있습니다.

## 빠른 시작

### 필수 조건

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (uvx 사용 시)

### 원격 실행 (uvx)

아래 클라이언트 설정은 모두 동일한 실행 정보를 사용합니다.
- `command`: `uvx`
- `args`: `["--from", "git+https://github.com/chabinhwang/toss-mcp", "toss-mcp"]`

#### Claude Code

설정 파일: `~/.claude/settings.json` (`mcpServers`에 추가)

```json
{
  "toss-docs": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp", "toss-mcp"]
  }
}
```

#### Codex

설정 파일: `~/.codex/config.toml` (`mcp_servers`에 추가)

```toml
[mcp_servers.toss-docs]
command = "uvx"
args = ["--from", "git+https://github.com/chabinhwang/toss-mcp", "toss-mcp"]
```

#### Gemini CLI

설정 파일: `~/.gemini/settings.json` (`mcpServers`에 추가)

```json
{
  "mcpServers": {
    "toss-docs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp", "toss-mcp"]
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
      "args": ["--from", "git+https://github.com/chabinhwang/toss-mcp", "toss-mcp"]
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

**소스 목록**

| 값 | 설명 |
|---|------|
| `apps_in_toss` | 앱인토스 |
| `tds_react_native` | TDS React Native |
| `tds_mobile` | TDS Mobile |

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

- 토스 개발자 문서 3개 소스 자동 수집 (앱인토스, TDS React Native, TDS Mobile)
- 마크다운 헤더 기반 지능형 청킹 (H1 → H2 → H3 재귀 분할)
- 2단계 키워드 검색 (정확 매칭 우선, 부분 매칭 폴백)
- SHA256 해시 기반 캐시로 빠른 재시작
- 비동기 병렬 수집 (동시 8개 요청)
- 아이콘 카탈로그 압축 리소스(`toss_mcp/data/toss_icons.json.gz`) 로드 지원

## 동작 방식

```
llms.txt / llms-full.txt 다운로드
       ↓
  링크 파싱 (seed) 또는 그대로 사용 (full)
       ↓
  하위 페이지 병렬 수집 (동시 8개)
       ↓
  마크다운 헤더 기반 청킹 (최대 3,000자)
       ↓
  로컬 캐시 저장 (~/.toss-mcp-cache/)
       ↓
  키워드 검색 제공
```

- **캐시**: SHA256 해시로 원본 변경을 감지하여, 변경이 없으면 캐시에서 즉시 로드합니다.
- **재동기화**: `sync_sources(force=True)` 호출 또는 캐시 디렉토리 삭제 후 재시작하면 됩니다.

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
    ├── cache.py         # JSON 캐시 + 해시 관리
    └── data/
        └── toss_icons.json.gz
```

## 라이선스

MIT License
