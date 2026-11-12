# `src/regulation/retriever.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/regulation/retriever.py` |
| 도메인 | `regulation` — 법령 도메인: RAG 검색과 법령 수동 갱신 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 460줄 (그중 1~86줄은 1일차 검색기를 주석으로 남긴 부분) |

## 1. 개요
법령 조문 RAG 검색기입니다(빌드 패턴 3). `data/laws/<법령>@<시행일>.md` 파일을 조문 단위 청크로 나누고, BM25(kiwipiepy 형태소)와 FAISS(Titan v2 임베딩) 순위를 RRF로 결합합니다. 쿼리 확장(실무 용어 → 조문 용어, 성분명↔CAS)과 선택적 LLM 리랭크를 거친 뒤, 질문 기준일(`as_of`)에 시행 중인 판은 "적용 조문", 기준일 이후 시행 판은 "시행 예정"으로 나눠 돌려줍니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`INDEX_DIR`, `LAW_DIR`, `MSDS_PATH`, `today`), `src.shared.llm` (`get_embeddings`, `get_chat_model`, 함수 안 지연 import)
- 이 모듈을 사용하는 곳:
  - `src/tools/msds_tools.py` (`search_law` → `search`)
  - `src/workflows/evidence.py` (`get_applicable`)
  - `src/workflows/pipeline_v1.py` (`get_chunk`, `retrieve`)
  - `src/regulation/refresh.py` (`load_chunks`, `_load_chunks_cached.cache_clear`, `get_index.cache_clear`, `INDEX_DIR`)
  - `src/api/app.py` (`_parse_front` — 화면에 법령 판 목록 표시)
  - `scripts/build_index.py` (`Chunk`, `load_chunks`)
  - `tests/test_retriever.py`, `tests/test_build_index.py`, `tests/test_law_refresh.py`, `tests/test_tools.py`
- 외부 라이브러리·서비스: `kiwipiepy`(형태소 분석), `rank_bm25.BM25Okapi`, `faiss`, `numpy`, `pydantic`(리랭크 구조화 출력), Bedrock 임베딩·채팅 모델(`src.shared.llm` 경유)

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `HEADER` | 상수 | 조문 머리 정규식 `## [doc_id] 제목` |
| `FRONT` | 상수 | 파일 앞머리(`---` 블록) 정규식 |
| `RRF_K` | 상수 | RRF 상수 60 |
| `QUERY_EXPANSION` | 상수 | 실무 표현 → 조문 표현 사전 (17개 항목) |
| `Chunk` | 클래스(dataclass) | 조문 한 판 (doc_id, 제목, 본문, 법령, 시행 기간 등) |
| `RetrievalResult` | 클래스(dataclass) | 검색 결과 (`as_of`, `applicable`, `upcoming`, `notes`, `method`) |
| `_parse_front()` | 함수 | 앞머리 메타데이터 파싱 |
| `parse_law_file()` | 함수 | 법령 파일 하나 → 청크 목록 |
| `assign_effective_to()` | 함수 | 같은 조문 판들의 `effective_to` 채우기 |
| `load_chunks()` / `_load_chunks_cached()` | 함수 | 법령 폴더 전체 청크 로딩 (캐시) |
| `get_chunk()` | 함수 | doc_id로 청크 하나 조회 |
| `get_applicable()` | 함수 | 조문 하나의 기준일 적용 판과 시행 예정 판 |
| `choose_version()` | 함수 | 판 목록에서 기준일 적용 판 선택 |
| `_substance_aliases()` | 함수 | 공개 성분명↔CAS 사전 (캐시) |
| `_mentions()` | 함수 | 성분명·CAS가 질문에 단어로 나오는지 |
| `expand_query()` | 함수 | 쿼리 확장 |
| `_kiwi()` / `KEEP_TAGS` / `tokenize()` | 함수 / 상수 / 함수 | 형태소 토크나이저 |
| `HybridIndex` | 클래스 | BM25 + FAISS 인덱스 |
| `rrf()` | 함수 | Reciprocal Rank Fusion 점수 |
| `get_index()` | 함수 | 기본 인덱스 생성 (캐시) |
| `RERANK_CANDIDATES` | 상수 | 리랭크 후보 수 6 |
| `llm_rerank()` | 함수 | LLM 리랭크 |
| `search()` | 함수 | 메인 검색 |
| `retrieve()` | 함수 | 기존 인터페이스: 적용 조문만 반환 |
| `to_contexts()` | 함수 | API Spec `contexts` 형식 변환 |

## 4. 상세 사양

### 4.1 `Chunk` (dataclass)
- 필드: `doc_id`, `title`, `text`, `law=""`, `short=""`, `article=""`, `status="현행"`, `effective_from: date | None`, `effective_to: date | None`
- `group` (property): doc_id에서 `@` 앞부분 — 판에 관계없이 같은 조문을 묶는 키 (예: `law:산안법:110`)
- `label(as_of=None) -> str`: 기준일 이후 시행 판이면 `"[시행 예정 YYYY-MM-DD] "`, 아니면 빈 문자열

### 4.2 `RetrievalResult` (dataclass)
- `as_of: date`, `applicable: list[Chunk]`(기준일 시행 중, 판정 근거), `upcoming: list[Chunk]`(기준일 이후 시행 예정, 따로 표시), `notes: list[str]`, `method: str = "bm25"`

### 4.3 청킹: `parse_law_file(text: str) -> list[Chunk]`
- 입력: 법령 파일 전체 텍스트
- 출력: 조문별 `Chunk` 목록
- 처리:
  1. 줄바꿈을 `\n`으로 통일
  2. `_parse_front`로 앞머리(`law`, `short`, `status`, `effective` 등 `키: 값`, 따옴표 제거) 파싱 후 본문에서 제거
  3. `effective`가 있으면 `effective_from`으로 변환
  4. `HEADER`(`## [doc_id] 제목`)마다 다음 머리 전까지를 한 청크로 자름. `text`는 `"<제목>\n<본문>"`
  5. `article`은 doc_id의 `@` 앞부분에서 마지막 `:` 뒤 값, `status` 기본값 `"현행"`
- 예외·오류 처리: 앞머리가 없으면 메타데이터 없이 진행. `effective` 형식 오류 시 `ValueError` (별도 처리 없음)

### 4.4 `assign_effective_to(chunks) -> list[Chunk]`
- 같은 `group`의 판들을 `effective_from` 순(없으면 가장 이른 것으로)으로 정렬하고, 다음 판 시행일 전날을 앞 판의 `effective_to`로 채웁니다.

### 4.5 `load_chunks(law_dir: Path = LAW_DIR) -> list[Chunk]`
- `law_dir`의 `*.md`를 이름순으로 읽어 `parse_law_file` → `assign_effective_to`. 경로 문자열별로 `lru_cache(maxsize=4)` 캐시(`_load_chunks_cached`)

### 4.6 `get_chunk(doc_id: str) -> Chunk | None`
- 기본 법령 폴더 청크 중 doc_id가 정확히 같은 것. 없으면 `None`

### 4.7 판 선택: `choose_version(versions, as_of) -> tuple[Chunk | None, list[Chunk]]`
- 출력: (`effective_from ≤ as_of`이거나 시행일이 없는 판 중 가장 최근 판 또는 `None`, `as_of` 이후 시행 판 목록)

### 4.8 `get_applicable(doc_id: str, as_of: date | None = None)`
- `as_of` 생략 시 `today()`. doc_id의 `group`에 속한 모든 판으로 `choose_version` 호출

### 4.9 쿼리 확장: `expand_query(question: str) -> str`
- 출력: `"<질문> <추가어...>"`
- 처리:
  1. `QUERY_EXPANSION`의 키가 질문에 부분 문자열로 들어 있으면 값 추가 (예: `MSDS`→`물질안전보건자료`, `재제출`→`변경 제출`, `고객사`→`양도 제공 상대방`, `영업비밀`→`비공개 대체자료 승인`)
  2. `_substance_aliases()`의 성분명·CAS가 `_mentions` 기준으로 질문에 나오면 짝(CAS↔성분명) 추가
- `_substance_aliases()`: `MSDS_PATH`(`products.json`)의 `section3` 성분 중 영업비밀이 아니고 CAS가 `\d{2,7}-\d{2}-\d` 형식인 것만. 파일 읽기·파싱 실패(`OSError`, `KeyError`, `JSONDecodeError`) 시 빈 사전
- `_mentions(question, name)`: 이름이 2글자 미만이면 거짓(예: `물`이 `물질`에 걸리는 문제 방지), 앞 글자가 한글·영숫자·`-`이면 다른 단어의 일부로 봄

### 4.10 `tokenize(text: str) -> list[str]`
- `Kiwi` 형태소 분석 결과 중 태그가 `KEEP_TAGS`(`NN`, `VV`, `VA`, `XR`, `SL`, `SN`, `SH`, `W_SERIAL`, `MAG`)로 시작하는 형태소만 소문자로 반환. `Kiwi` 객체는 한 번만 생성(캐시)

### 4.11 `HybridIndex(chunks, vectors=None)`
- 생성: 청크마다 토큰화 → `BM25Okapi`. `vectors`가 있고 개수가 청크 수와 같으면 L2 정규화 후 `faiss.IndexFlatIP`(코사인 유사도)에 추가, 아니면 `faiss = None`
- `bm25_ranks(query) -> list[int]`: BM25 점수 내림차순 청크 번호 중 질의 토큰과 하나라도 겹치는 청크만
- `vector_ranks(query, embed=None, top=20) -> list[int]`: FAISS가 없으면 빈 목록. `embed`를 안 주면 `get_embeddings().embed_query` 사용. 질의 벡터를 정규화해 상위 `top`개 검색

### 4.12 `rrf(rank_lists, k=RRF_K) -> dict[int, float]`
- 각 순위 목록에서 순위 r(0부터)마다 `1 / (k + r + 1)`을 더한 점수

### 4.13 `get_index() -> HybridIndex`
- `load_chunks()` 청크와 `INDEX_DIR/chunks.json`의 doc_id 순서가 같고 `vectors.npy`가 있으면 벡터를 함께 씀, 아니면 BM25만. `lru_cache(maxsize=1)` 캐시

### 4.14 `llm_rerank(question, chunks, model=None) -> list[str]`
- 입력: 질문, 후보 청크, 모델(생략 시 `get_chat_model(max_tokens=300)`)
- 출력: 재정렬한 doc_id 목록
- 처리: 1. 후보마다 `[doc_id] 본문 앞 600자` 목록으로 프롬프트 작성 2. `Ranking(doc_ids: list[str])` 구조화 출력으로 호출(`with_retry`가 있으면 최대 2회) 3. 후보에 없는 doc_id는 버리고, LLM이 빠뜨린 후보는 원래 순서로 뒤에 붙임
- 예외·오류 처리: 이 함수 안에서는 처리하지 않음 (`search`가 잡음)

### 4.15 `search(question, k=3, as_of=None, index=None, embed=None, rerank=False, rerank_model=None) -> RetrievalResult`
- 입력: 질문, 조문 수 `k`, 기준일(생략 시 `today()`), 인덱스(생략 시 `get_index()`), 임베딩 함수, 리랭크 여부, 리랭크 모델 (`index`·`embed`·`rerank_model`은 테스트 주입용으로 쓰임)
- 출력: `RetrievalResult`
- 처리:
  1. `expand_query`로 질의 확장
  2. BM25 순위 계산, 벡터 순위가 있으면 추가해 `method="bm25+faiss"`
  3. `rrf`로 결합
  4. 조문 그룹 점수 = 그 조문 판들 중 최고 점수 → 그룹 순위
  5. `rerank=True`이고 그룹이 2개 이상이면 상위 `max(k, 6)`개 그룹의 대표 판(기준일 적용 판, 없으면 첫 판)을 `llm_rerank`로 재정렬, `method`에 `+rerank`
  6. 상위 `k`개 그룹마다 `choose_version`으로 적용 판은 `applicable`, 시행 예정 판은 `upcoming`에 담음
- 예외·오류 처리:
  - 벡터 검색 예외 → BM25만 사용, `method = "bm25 (벡터 검색 실패: <오류 종류>)"`
  - 리랭크 예외 → 원래 순위 유지, `method`에 `" (리랭크 실패: <오류 종류>)"`
  - 기준일이 수집한 가장 이른 판보다 앞서면 가장 이른 판을 적용 조문으로 쓰고 `notes`에 "<조문>: 기준일 <as_of> 당시 판은 수집하지 않아 <시행일> 시행 판으로 답합니다." 추가

### 4.16 `retrieve(question, k=3, as_of=None) -> list[Chunk]`
- 기존 인터페이스 유지용. `search(...).applicable`만 반환 (리랭크 없음)

### 4.17 `to_contexts(result) -> list[dict[str, str]]`
- API Spec `contexts` 형식 `[{doc_id, text}]`. 적용 조문은 본문 그대로, 시행 예정 조문은 `label(as_of)`(`[시행 예정 YYYY-MM-DD] `)을 앞에 붙임

## 5. 데이터·설정
- 읽는 파일: `data/laws/*.md`(`LAW_DIR`), `data/msds/products.json`(`MSDS_PATH`, 성분명↔CAS), `index/chunks.json`, `index/vectors.npy`(`INDEX_DIR`, `scripts/build_index.py`가 생성)
- 쓰는 파일: 없음
- 환경 변수: 이 파일에서 직접 읽지 않음. 리랭크 사용 여부는 호출부 `msds_tools.search_law`의 `MSDS_RERANK`로 결정. Bedrock 설정은 `src.shared.llm`/`src.shared.config` 담당
- 주요 상수: `RRF_K = 60`, `RERANK_CANDIDATES = 6`, `vector_ranks` 기본 `top = 20`, 리랭크 본문 600자, 리랭크 모델 `max_tokens=300`

## 6. 처리 흐름
```
question
 → expand_query (용어 사전 + 성분명↔CAS)
 → BM25 순위 ─┐
 → FAISS 순위 ─┴→ RRF 결합 (벡터 실패 시 BM25만)
 → 조문 그룹별 최고 점수로 정렬
 → [rerank] 상위 max(k,6)개 대표 판을 LLM이 재정렬 (실패 시 원래 순위)
 → 상위 k개 그룹마다 choose_version(as_of)
     ├ applicable: 기준일 시행 중 판 (없으면 가장 이른 판 + notes)
     └ upcoming: 기준일 이후 시행 판
 → RetrievalResult → (호출부) to_contexts / search_law dict
```
단독 실행: `python -m src.regulation.retriever <질문>` → `method`, `as_of`, 적용·예정 조문 출력

## 7. 제약·주의 사항
- 캐시: `_load_chunks_cached`(경로별 4개), `get_index`, `_substance_aliases`, `_kiwi`는 `lru_cache`라 법령 파일이 바뀌어도 자동 갱신되지 않습니다. `refresh.py`가 `_load_chunks_cached.cache_clear()`, `get_index.cache_clear()`를 호출합니다. `_substance_aliases`는 비우는 곳이 없습니다(제품 성분 변경 반영 여부 확인 필요).
- 벡터는 `index/chunks.json`의 doc_id 순서가 현재 청크와 정확히 같을 때만 씁니다. 다르면 조용히 BM25만 씁니다.
- 판정 근거는 `applicable`만 쓰고 `upcoming`은 따로 표시합니다(모듈 주석).
- 영업비밀 성분은 쿼리 확장 사전에 넣지 않습니다.
- `get_chunk`, `get_applicable`, `get_index`는 기본 `LAW_DIR`만 봅니다.

## 8. 관련 테스트
- `tests/test_retriever.py`: `test_parse_and_effective_to`, `test_choose_version_by_as_of`, `test_search_splits_applicable_and_upcoming`, `test_search_before_earliest_snapshot_adds_note`, `test_vector_failure_falls_back_to_bm25`, `test_rerank_reorders_and_ignores_unknown_ids`, `test_rerank_failure_keeps_original_order`, `test_rrf_rewards_agreement`, `test_expand_query_terms_and_cas_alias`, `test_tokenize_keeps_content_words`, `test_real_data_loaded_with_versions`, `test_real_data_bm25_recall_at_3`(옛 평가셋 v1 BM25 recall@3 ≥ 0.8), `test_live_hybrid_top1`(`@pytest.mark.live`, 실제 Titan 임베딩 필요)
- `tests/test_tools.py`: `test_search_law_returns_applicable_and_upcoming`
- `tests/test_build_index.py`: `test_build_writes_vectors_and_meta`, `test_build_reports_embedding_failure`
- `tests/test_law_refresh.py`: 캐시 비우기 확인(픽스처에서 `cache_clear` 호출)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `0574139` | 1일차: 표준 라이브러리 문자 bigram 코사인 검색 스케치 (`src/retriever.py`, `load_chunks`, `get_chunk`, `expand_query`, `retrieve`) |
| `3c00663` | 2일차: BM25(kiwipiepy) + FAISS(Titan v2) RRF 하이브리드, 쿼리 확장 사전 확대·성분명↔CAS, LLM 리랭크, 시행일 기준 판 선택으로 교체. 1일차 코드는 주석으로 보관 |
| `3c00663` (주석) | `expand_query`: 성분명 부분 문자열 일치 → `_mentions` 단어 일치로 교체 (`물`이 `물질`에 걸리는 문제) |
| `3c00663` (주석) | `bm25_ranks`: 점수 > 0 필터 → 질의 토큰 겹침 필터로 교체 (흔한 단어의 IDF가 0 이하가 되어 결과가 비는 문제) |
| `97ab1fd` | 도메인별 폴더 리팩토링: `src/retriever.py` → `src/regulation/retriever.py`, `src.config`·`src.llm` → `src.shared.config`·`src.shared.llm` |
