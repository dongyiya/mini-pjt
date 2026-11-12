# `src/tools/mcp_client.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/tools/mcp_client.py` |
| 도메인 | `tools` — 에이전트가 호출하는 도메인 도구와 MCP 서버·클라이언트 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 106줄 |

## 1. 개요
`src/tools/mcp_server.py`에 stdio로 붙어 MCP 도구를 동기 LangChain 도구(`StructuredTool`)로 제공하는 브리지입니다. 백그라운드 스레드의 이벤트 루프에서 MCP 세션 하나(서버 프로세스 1개)를 계속 열어 두고, 동기로 도는 에이전트 그래프의 도구 호출을 그 루프로 넘깁니다. 서버를 띄우지 못하면 `None`을 돌려주고, 에이전트는 로컬 도구로 대신합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`ROOT`); 하위 프로세스로 `src.tools.mcp_server` 실행
- 이 모듈을 사용하는 곳:
  - `src/agents/brains.py` (`make_tools`에서 `get_mcp_tools()` 지연 import)
  - `tests/test_mcp.py`
- 외부 라이브러리·서비스: `langchain_mcp_adapters.client.MultiServerMCPClient`, `langchain_mcp_adapters.tools.load_mcp_tools`, `langchain_core.tools.StructuredTool`, 표준 라이브러리 `asyncio`, `threading`, `json`, `sys`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `_text()` | 함수 | MCP 도구 결과(문자열·튜플·content 블록 목록)를 문자열로 변환 |
| `McpBridge` | 클래스 | 백그라운드 스레드에서 MCP 세션을 유지하고 동기 호출을 제공 |
| `_bridge` | 모듈 변수 | 프로세스당 하나인 브리지 (`None`=미시도, `False`=실패, 객체=연결됨) |
| `_lock` | 모듈 변수 | `_bridge` 초기화용 `threading.Lock` |
| `get_mcp_tools()` | 함수 | 프로세스당 한 번 연결해 이름 → 동기 도구 dict 반환, 실패 시 `None` |

## 4. 상세 사양

### 4.1 `McpBridge(timeout: float = 30.0)`
- 속성: `timeout`, `loop`(새 이벤트 루프), `ready`(`threading.Event`), `stop_event`(`asyncio.Event`, 세션 연결 후 생성), `tools`(MCP 도구 목록), `error`(연결 오류), `thread`(이름 `mcp-bridge`, daemon 스레드)

#### 4.1.1 `start() -> McpBridge`
- 처리: 1. 스레드 시작(`_run`) 2. `ready`를 `timeout`초 대기 3. `error`가 있으면 다시 발생 4. 자신을 반환
- 예외·오류 처리: 시간 안에 준비되지 않으면 `TimeoutError("MCP 서버 연결 시간 초과")`. 세션 연결 중 오류는 `self.error`로 받아 그대로 raise

#### 4.1.2 `_run()` / `_session()` (내부)
- `_run`: 스레드에서 이벤트 루프를 설정하고 `_session()`을 끝날 때까지 실행
- `_session`:
  1. `MultiServerMCPClient({"msds": {"command": sys.executable, "args": ["-X", "utf8", "-m", "src.tools.mcp_server"], "transport": "stdio", "cwd": str(ROOT)}})` 생성
  2. `client.session("msds")`를 열고 `load_mcp_tools(session)`로 도구 로딩
  3. `stop_event` 생성 후 `ready.set()`
  4. `stop_event`가 설정될 때까지 세션 유지
- 예외·오류 처리: `BaseException`을 잡아 `self.error`에 저장하고 `ready.set()` (→ `start()`에서 raise)

#### 4.1.3 `call(tool, args: dict) -> str`
- 입력: MCP 도구 객체, 인자 dict
- 출력: 결과 문자열 (`_text()` 변환)
- 처리: `asyncio.run_coroutine_threadsafe(tool.ainvoke(args), self.loop)`로 브리지 루프에서 실행하고 `timeout`초까지 결과 대기
- 예외·오류 처리: 별도 처리 없음 (대기 시간 초과·도구 오류는 호출자에게 전달)

#### 4.1.4 `langchain_tools() -> dict[str, Any]`
- 출력: `{도구 이름: StructuredTool}` — 이름·설명·`args_schema`는 MCP 도구 것을 그대로 쓰고, 함수는 `self.call(도구, kwargs)`
- 처리: 반복문 변수 캡처 문제를 피하려고 기본 인자(`_t=t`)로 도구를 묶습니다.

#### 4.1.5 `close() -> None`
- 처리: `stop_event`가 있으면 루프 스레드에서 설정해 세션을 끝내고, 스레드를 최대 5초 join

### 4.2 `get_mcp_tools() -> dict[str, Any] | None`
- 입력: 없음
- 출력: 연결 성공 시 `McpBridge.langchain_tools()` 결과, 실패 시 `None`
- 처리: 1. `_lock` 획득 2. `_bridge`가 `None`이면 `McpBridge().start()` 시도 3. 성공하면 보관, 실패하면 `_bridge = False`
- 예외·오류 처리: 연결 실패 시 표준 오류에 `[경고] MCP 서버 연결 실패, 로컬 도구 사용: <오류 종류>: <메시지>`를 출력하고 `None` 반환. 한 번 실패하면 같은 프로세스에서 다시 시도하지 않습니다.

### 4.3 `_text(result) -> str` (내부)
- 문자열이면 그대로, 튜플이면 첫 요소(content)만 사용, 목록이면 각 블록의 `text`를 이어 붙임(dict는 `get("text")`, 객체는 `.text`, 없으면 `str`), 그 밖은 `json.dumps(..., ensure_ascii=False)`

## 5. 데이터·설정
- 읽는 파일: 없음
- 쓰는 파일: 없음
- 환경 변수: 이 파일에서는 읽지 않음. 사용 여부는 호출부 `src/agents/brains.py`의 `MSDS_USE_MCP`(`"0"`이면 사용 안 함, 기본 사용)로 결정
- 주요 상수: 기본 `timeout` 30.0초, 서버 이름 키 `"msds"`, 작업 디렉터리 `ROOT`

## 6. 처리 흐름
```
brains.make_tools() ── MSDS_USE_MCP != "0" ──> get_mcp_tools()
  └─ (최초 1회) McpBridge().start()
       └─ mcp-bridge 스레드: MultiServerMCPClient → python -m src.tools.mcp_server (stdio)
            └─ load_mcp_tools → ready.set() → stop_event 대기
  └─ langchain_tools() → {이름: StructuredTool}
에이전트 도구 호출 → StructuredTool.func → McpBridge.call → (브리지 루프) tool.ainvoke → _text → 문자열
연결 실패 → None → brains는 로컬 msds_tools 도구 사용
```

## 7. 제약·주의 사항
- 프로세스당 서버 프로세스 1개, 세션 1개를 공유합니다. 브리지 스레드는 daemon입니다.
- 실패 결과(`_bridge = False`)도 캐시되어 재시도하지 않습니다(테스트 `test_get_mcp_tools_falls_back_on_failure`가 확인).
- `get_mcp_tools()`는 `close()`를 호출하지 않습니다. 정리 시점은 코드에 없습니다(확인 필요).
- 모듈 docstring의 옛 경로를 `src/tools/mcp_server.py`, `src/agents/brains.py`(`make_tools`)로 고쳤습니다 (2026-11-12 정리 완료).

## 8. 관련 테스트
- `tests/test_mcp.py`: `bridge` 픽스처(`McpBridge(timeout=60).start()`), `test_server_exposes_expected_tools`, `test_mcp_results_match_local_tools`, `test_mcp_keeps_masking`, `test_make_tools_uses_mcp_when_enabled`, `test_make_tools_local_when_disabled`, `test_get_mcp_tools_falls_back_on_failure`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차: MCP 클라이언트 브리지 추가 (`src/mcp_client.py`) |
| `97ab1fd` | 도메인별 폴더 리팩토링: `src/mcp_client.py` → `src/tools/mcp_client.py`, `from src.config import ROOT` → `from src.shared.config import ROOT`, 서버 실행 인자 `-m src.mcp_server` → `-m src.tools.mcp_server` |
