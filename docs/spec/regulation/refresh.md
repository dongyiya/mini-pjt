# `src/regulation/refresh.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/regulation/refresh.py` |
| 도메인 | `regulation` — 법령 도메인: RAG 검색과 법령 수동 갱신 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 113줄 |

## 1. 개요
UI의 '법령 가져오기' 버튼에 해당하는 법령 수동 갱신 기능입니다. API Spec을 바꾸지 않기 위해 별도 엔드포인트 없이 `POST /query`에 `{"question": "법령 갱신"}`을 보내면 실행합니다(2026-11-12 사용자 결정). 국가법령정보센터에서 대상 법령을 다시 받아 `data/laws`를 바꾸고, 갱신 전후 조문을 비교한 뒤, 검색 인덱스를 다시 만들고 검색기 캐시를 비웁니다. LLM은 쓰지 않고(임베딩만), 동시에 두 번 실행되지 않도록 잠급니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.regulation.retriever` (`load_chunks`, `_load_chunks_cached`, `get_index`, `INDEX_DIR`), `src.shared.config` (`LAW_DIR`, `get_settings`, `today`)
- 함수 안에서 불러오는 스크립트: `scripts.collect_data.refresh_laws`, `scripts.build_index.build` (CLAUDE.md의 의존 방향 예외로 명시됨)
- 이 모듈을 사용하는 곳:
  - `src/workflows/graph.py` (`run_query`에서 `is_refresh_command` → `refresh()`)
  - `tests/test_law_refresh.py`
- 외부 라이브러리·서비스: 국가법령정보센터 API(`scripts/collect_data.py` 경유), 임베딩(`scripts/build_index.py` 경유), 표준 라이브러리 `re`, `threading`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `COMMAND` | 상수 | '법령 갱신' 명령 정규식 |
| `_lock` | 모듈 변수 | 동시 실행 방지 `threading.Lock` |
| `is_refresh_command()` | 함수 | 질문이 갱신 명령인지 판별 |
| `snapshot()` | 함수 | 현재 법령 폴더의 `{doc_id: 본문}` |
| `diff()` | 함수 | 갱신 전후 추가·삭제·변경 doc_id |
| `_step()` | 함수 | trace 단계 dict 생성 (출력 1500자 제한) |
| `refresh()` | 함수 | 갱신 실행, `{answer, contexts, trace}` 반환 |
| `render_answer()` | 함수 | 사용자에게 보여 줄 답변 문장 작성 |

## 4. 상세 사양

### 4.1 `is_refresh_command(question: str) -> bool`
- `COMMAND` 정규식: 앞뒤 공백 허용, `법령` + (`갱신`|`가져오기`|`업데이트`|`수집`|`새로 고침`) + 선택적 (`해 줘`|`하기`|`실행`) + 선택적 `.`/`!`, 문장 전체가 일치해야 함
- 예: `"법령 갱신"`, `"법령 업데이트 해줘"`, `" 법령갱신 "` → 참 / `"법령 갱신 주기는?"`, `"MSDS 법령 알려줘"` → 거짓 (테스트 `test_command`)

### 4.2 `snapshot(law_dir: Path = LAW_DIR) -> dict[str, str]`
- 처리: `retriever._load_chunks_cached` 캐시를 비우고 `load_chunks(law_dir)`를 다시 읽어 `{doc_id: text}` 반환

### 4.3 `diff(before, after) -> dict[str, list[str]]`
- 출력: `{"added": after에만 있는 doc_id, "removed": before에만 있는 doc_id, "changed": 둘 다 있고 본문이 다른 doc_id}` (각각 정렬)

### 4.4 `refresh(collect=None, build=None, law_dir=LAW_DIR) -> dict`
- 입력: `collect` 수집 함수(결과 목록 반환), `build` 인덱스 생성 함수(0이면 성공), `law_dir` 법령 폴더. 생략 시 실제 스크립트 사용 (테스트에서 가짜 함수 주입)
- 출력: API Spec 모양 `{answer, contexts, trace}`
  - `contexts`: 추가·변경된 조문의 `{doc_id, text}` (갱신 후 본문)
  - `trace`: `law_refresh_collect`(법령별), `law_refresh_diff`, `law_refresh_index` 단계
- 처리:
  1. `_lock`을 기다리지 않고 획득 시도
  2. `collect`가 없으면 `get_settings().law_api_oc` 확인 후 `refresh_laws(out_dir=law_dir)` 사용, `build`가 없으면 `scripts.build_index.build` 사용
  3. 갱신 전 `snapshot` → `collect()` → 갱신 후 `snapshot` → `diff`
  4. 수집 결과마다 trace: 실패면 `"실패: <error>"`, 성공이면 판별 `"<status> <effective> 조문 <N>개"`
  5. 바뀐 조문이 있거나 `INDEX_DIR/vectors.npy`가 없으면 `build()` 실행(반환값 0이면 성공), 아니면 인덱스 그대로 사용
  6. `retriever._load_chunks_cached`, `retriever.get_index` 캐시 비움 → 다음 질문부터 새 조문으로 검색
  7. `render_answer`로 답변 작성, 잠금 해제(`finally`)
- 예외·오류 처리:
  - 이미 실행 중 → `answer`: "법령 갱신이 이미 진행 중입니다. 잠시 후 다시 시도해 주세요.", trace 출력 "이미 진행 중"
  - `LAW_API_OC` 없음(수집 함수 미주입 시) → `answer`: "법령 API 키(LAW_API_OC)가 없어 법령을 가져올 수 없습니다. 기존 조문을 그대로 씁니다."
  - 법령별 수집 실패(`ok: False`) → 해당 법령만 실패로 알리고 기존 조문 유지
  - 인덱스 생성 실패(`build() != 0`) → trace "실패 → BM25만 사용", 답변에 BM25만 쓴다고 안내
  - `collect()`·`build()`가 예외를 던지는 경우는 별도로 잡지 않고 잠금만 해제됩니다.

### 4.5 `render_answer(results, d, index_ok, changed_any) -> str`
- 첫 줄: "법령을 다시 가져왔습니다 (가져온 날 <today>)."
- 법령마다: 실패면 "가져오기 실패, 기존 조문을 그대로 씁니다 (<error>)." / 성공이면 현행 판 시행일·조문 수와 시행 예정 판(시행일, 바뀌는 조문 목록) 또는 "내용이 바뀌는 시행 예정 판 없음"
- 바뀐 조문이 있으면 "바뀐 조문: 추가 ... / 변경 ... / 삭제 ..."와 인덱스 재생성 결과, 없으면 "바뀐 조문은 없습니다."

### 4.6 `_step(name, inp, out) -> dict` (내부)
- `{"step": name, "input": inp, "output": out[:1500]}`

## 5. 데이터·설정
- 읽는 파일: `data/laws/*.md`(`LAW_DIR` 또는 `law_dir`), `index/vectors.npy` 존재 여부
- 쓰는 파일: 직접 쓰지 않음. `refresh_laws`가 `data/laws`를, `build_index.build`가 `index/`를 씀
- 환경 변수: `LAW_API_OC` (`get_settings().law_api_oc`로 확인, 값은 출력하지 않음)
- 주요 상수: `COMMAND` 정규식, trace 출력 최대 1500자
- 수집 결과 항목 형식(코드에서 쓰는 키): `law`, `ok`, `error`, `versions[{status, effective, articles}]`

## 6. 처리 흐름
```
POST /query {"question": "법령 갱신"}
 → graph.run_query → is_refresh_command → refresh()
    1) 잠금 (실패 시 "이미 진행 중")
    2) LAW_API_OC 확인 (없으면 종료)
    3) snapshot(전) → refresh_laws → snapshot(후) → diff
    4) 바뀜 있음 또는 vectors.npy 없음 → build_index
    5) retriever 캐시 비움
    6) {answer: render_answer(...), contexts: 추가·변경 조문, trace}
```

## 7. 제약·주의 사항
- 같은 프로세스에서 동시 실행은 `threading.Lock`으로 거부합니다(대기하지 않음). 여러 프로세스 간 잠금은 없습니다.
- 캐시 비우기는 이 프로세스의 retriever 캐시만 대상입니다. MCP 서버 등 다른 프로세스에는 영향 없음(MCP 서버는 법령 검색 도구를 노출하지 않음).
- `retriever._substance_aliases` 캐시는 비우지 않습니다(법령과 무관).
- `scripts/` 모듈을 함수 안에서 불러오는 것은 CLAUDE.md에 적힌 의존 방향 예외입니다.
- 대상 법령 목록은 `scripts/collect_data.py`가 정합니다(이 파일에 없음).

## 8. 관련 테스트
- `tests/test_law_refresh.py` (가짜 수집·인덱스 함수, 네트워크·LLM 없음): `test_command`(명령 판별 6가지), `test_no_change_keeps_index`, `test_changed_and_upcoming_rebuilds_index`, `test_failed_law_and_failed_index`, `test_concurrent_refresh_is_refused`, `test_missing_api_key`, `test_run_query_routes_refresh_command`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차: 법령 수동 갱신 추가 (`src/law_refresh.py`) |
| `97ab1fd` | 도메인별 폴더 리팩토링: `src/law_refresh.py` → `src/regulation/refresh.py`, `from src import retriever` → `from src.regulation import retriever`, `src.config` → `src.shared.config` |
