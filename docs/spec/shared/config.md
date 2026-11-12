# `src/shared/config.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/shared/config.py` |
| 도메인 | `shared` — 여러 도메인이 함께 쓰는 설정·LLM·날짜·trace 공통 기능 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 57줄 |

## 1. 개요
프로젝트 설정을 한곳에서 읽는 모듈입니다. 상위 폴더(`sds-ax-practice`)의 `.env`를 불러오고, 데이터·인덱스·체크포인트 경로 상수, 모델 ID 등 환경 변수 기반 설정(`Settings`), 질문 기준일 기본값(`today()`)을 제공합니다. 프로젝트 안에 새 `.env`를 만들지 않는다는 원칙이 docstring에 적혀 있습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: 없음
- 이 모듈을 사용하는 곳:
  - `src/shared/llm.py` (`get_settings`), `src/shared/dates.py` (`today`)
  - `src/memory/checkpointer.py` (`CHECKPOINT_DB`)
  - `src/guardrails/guard.py` (`MSDS_PATH`)
  - `src/api/app.py` (`LAW_DIR`)
  - `src/regulation/refresh.py` (`LAW_DIR`, `get_settings`, `today`), `src/regulation/retriever.py` (`INDEX_DIR`, `LAW_DIR`, `MSDS_PATH`, `today`)
  - `src/revision/msds_apply.py` (`MSDS_PATH`, `today`), `src/revision/preview.py` (`SUBSTANCE_DIR`)
  - `src/tools/mcp_client.py` (`ROOT`), `src/workflows/evidence_text.py` (`ROOT`)
  - `scripts/build_index.py` (`INDEX_DIR`), `scripts/collect_data.py` (`LAW_DIR`, `get_settings`, `today`), `scripts/collect_substances.py` (`MSDS_PATH`, `SUBSTANCE_DIR`, `get_settings`, `today`)
  - `tests/test_config.py`, `tests/test_retriever.py` (`ROOT`)
- 외부 라이브러리·서비스: `python-dotenv` (`load_dotenv`), 표준 라이브러리 `os`, `dataclasses`, `datetime`, `pathlib`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `ROOT` | 상수 | 프로젝트 루트(`mini-pjt`) 경로 |
| `ENV_PATH` | 상수 | 상위 폴더의 `.env` 경로 |
| `DATA_DIR` | 상수 | `ROOT / "data"` |
| `LAW_DIR` | 상수 | `data/laws` (법령 파일 폴더) |
| `SUBSTANCE_DIR` | 상수 | `data/substances` |
| `MSDS_PATH` | 상수 | `data/msds/products.json` |
| `UPDATES_PATH` | 상수 | `data/regulation_updates.json` |
| `INDEX_DIR` | 상수 | `ROOT / "index"` |
| `CHECKPOINT_DB` | 상수 | `ROOT / "checkpoints.sqlite"` |
| `DEFAULT_EMBED_MODEL` | 상수 | `"amazon.titan-embed-text-v2:0"` |
| `Settings` | 클래스(frozen dataclass) | 환경 변수 기반 설정 묶음 |
| `get_settings()` | 함수 | 환경 변수를 읽어 `Settings` 생성 |
| `today()` | 함수 | 질문 기준일 기본값 |

## 4. 상세 사양
### 4.1 모듈 로드 시 동작
- 처리:
  1. `ROOT = Path(__file__).resolve().parents[2]` 로 `mini-pjt` 경로를 구합니다.
  2. `ENV_PATH = ROOT.parent / ".env"` 를 `load_dotenv(ENV_PATH, override=False)` 로 읽습니다. 이미 설정된 환경 변수는 덮어쓰지 않습니다.
- 예외·오류 처리: `.env`가 없을 때의 처리는 `load_dotenv` 기본 동작을 따릅니다(코드에 별도 처리 없음).

### 4.2 `Settings`
- 입력: 필드 `aws_region`, `bedrock_model_id`, `embed_model_id`, `law_api_oc`, `data_go_kr_key`, `langsmith_project` (모두 `str`)
- 출력: 변경 불가(`frozen=True`) 데이터 객체
- 처리: 해당 없음(데이터 보관만)
- 예외·오류 처리: 생성 후 필드 수정 시 dataclass 기본 오류 발생

### 4.3 `get_settings() -> Settings`
- 입력: 없음(환경 변수 사용)
- 출력: `Settings`
- 처리: 호출할 때마다 환경 변수를 다시 읽습니다(테스트에서 바꾸기 쉽도록). 기본값은 다음과 같습니다.
  1. `aws_region` ← `AWS_DEFAULT_REGION`, 기본 `"us-east-1"`
  2. `bedrock_model_id` ← `BEDROCK_MODEL_ID`, 기본 `"us.anthropic.claude-sonnet-4-6"`
  3. `embed_model_id` ← `BEDROCK_EMBED_MODEL_ID`, 기본 `DEFAULT_EMBED_MODEL`
  4. `law_api_oc` ← `LAW_API_OC`, 기본 `""`
  5. `data_go_kr_key` ← `DATA_GO_KR_API_KEY`, 기본 `""`
  6. `langsmith_project` ← `LANGSMITH_PROJECT`, 기본 `"mini-pjt"`
- 예외·오류 처리: 없음(값이 없으면 기본값)

### 4.4 `today() -> date`
- 입력: 없음(환경 변수 `MSDS_TODAY`)
- 출력: `date`
- 처리: `MSDS_TODAY`(YYYY-MM-DD)가 있으면 `date.fromisoformat`으로 변환해 돌려주고, 없으면 `date.today()`를 돌려줍니다. 평가 재현용으로 날짜를 고정할 때 씁니다.
- 예외·오류 처리: `MSDS_TODAY` 형식이 잘못되면 `date.fromisoformat`의 `ValueError`가 그대로 올라갑니다(별도 처리 없음).

## 5. 데이터·설정
- 읽는 파일: `../.env` (`sds-ax-practice/.env`)
- 쓰는 파일: 없음
- 환경 변수: `AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_EMBED_MODEL_ID`, `LAW_API_OC`, `DATA_GO_KR_API_KEY`, `LANGSMITH_PROJECT`, `MSDS_TODAY`
- 주요 상수: 3절 표의 경로 상수와 `DEFAULT_EMBED_MODEL`

## 6. 처리 흐름
1. import 시 `ROOT`·`ENV_PATH` 계산 → `.env` 로드(기존 환경 변수 우선)
2. 경로 상수 정의
3. 다른 모듈이 필요할 때 `get_settings()` / `today()` 호출 → 그때마다 환경 변수 조회

## 7. 제약·주의 사항
- `get_settings()`는 캐시하지 않습니다. 다만 이를 쓰는 `src/shared/llm.py`의 `get_chat_model`·`get_embeddings`는 `lru_cache`로 결과를 캐시하므로, 환경 변수를 바꾼 뒤에는 그쪽 캐시를 비워야 반영됩니다(`tests/test_llm.py` 참고).
- `ROOT`는 파일 위치(`src/shared/config.py`) 기준 `parents[2]`이므로 파일을 옮기면 계산식을 바꿔야 합니다(97ab1fd에서 실제로 변경됨).
- `.env`는 프로젝트 밖(상위 폴더)에 있습니다.

## 8. 관련 테스트
- `tests/test_config.py`: `test_paths_point_inside_project`, `test_settings_read_env`, `test_settings_defaults`, `test_today_can_be_fixed`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차: 에이전트 그래프·RAG·MCP·HITL·평가 구현 (당시 `src/config.py`) |
| `97ab1fd` | 도메인별 폴더 구조 리팩토링으로 `src/shared/config.py`로 이동. `ROOT` 계산을 `parent.parent` → `parents[2]`로 변경 (기존 코드 주석으로 남김) |
