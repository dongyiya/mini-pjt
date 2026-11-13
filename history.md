# 작업 기록 (history)

채팅에서 진행한 작업을 순서대로 적습니다. 규칙은 [CLAUDE.md](CLAUDE.md) "추가 규칙"을 따릅니다. 기존 기록은 고치지 않고 아래에 추가만 합니다.

## 2026-11-13

### 1. 승인 흐름 시험용 가상 법령 개정 U-06 추가
- 요청: 어시스턴트의 승인 요청을 시험해 보려고 가상 법령을 하나 추가
- 한 일: `data/regulation_updates.json`에 U-06을 추가함
  - [가상] 산업안전보건법 시행규칙 개정. '특별관리물질' 명칭을 '특별관리 유해인자'로 바꾼다고 가정(시행 2026-12-01 가정, `real: false`)
  - 영향 제품: P-003(포름알데히드), P-005(벤젠). 15번 항목 산업안전보건법 표기를 교체하는 `replace` 변경 작업 포함(대체 표기 입력 필요)
  - ID를 U-05가 아닌 U-06으로 정함. 평가셋 11번이 "U-05는 없는 사건"이라고 안내하는지 검사하기 때문
- 결과: `assess_update`와 `update_ops`에서 P-003, P-005가 나오는 것을 확인함. 재제출 대상은 아님(규제현황 변경은 시행규칙 제159조에 해당하지 않음)

### 2. 서비스 구동
- 요청: 서비스 구동
- 한 일: `./run.sh serve`로 서버를 실행함(포트 8000)
- 결과: http://localhost:8000/ 응답 200, 화면에 U-06이 나오는 것을 확인함

### 3. 제품 MSDS를 원래 데모 데이터로 되돌림
- 요청: 원래 데모 데이터로 되돌리기
- 한 일: `./run.sh reset-msds` 실행
- 바뀐 파일: `data/msds/products.json`(원본 파일과 같아짐), `data/msds/history/`·`revision_log.json` 삭제
- 결과: 켜져 있는 서버 화면에도 원래 데이터가 보이는 것을 확인함. U-06은 남아 있었음

### 4. U-06 삭제
- 요청: 평가를 다시 돌릴 예정이라 U-06 삭제
- 한 일: `data/regulation_updates.json`에서 U-06과 `_note`의 U-06 설명을 지움. 서버가 U-06을 계속 보여 줘서 재시작함
- 결과: 변경 사건이 U-01~U-04만 남음. 커밋된 원래 내용과 같음(git diff 없음)

### 5. 승인·반려 내역 삭제
- 요청: 승인되거나 반려된 내역 삭제
- 한 일: 서버를 멈추고 `checkpoints.sqlite`(및 `-shm`, `-wal`)를 스크래치패드 백업 폴더로 옮긴 뒤 서버를 재시작함
  - 백업 위치: `C:\Users\Admin\AppData\Local\Temp\claude\85161c47a7720728\adedf645-91eb-4436-bd39-5a974d6dea45\scratchpad\checkpoints_backup`
- 결과: 서버의 승인 대기 건이 0건인 것을 확인함
- 남은 일: 브라우저 저장소(localStorage `msds.reqs`)의 승인함 목록은 사용자가 직접 지워야 함
  - 개발자 도구 콘솔에서 `localStorage.removeItem("msds.reqs"); location.reload();` 실행

### 6. 평가 실행 (진행 중)
- 요청: 평가 진행
- 한 일: 최종으로 확정한 2차 보고서를 덮어쓰지 않도록 3차로 실행함(`python -m evaluation.run_eval --round 3`)
- 결과 파일: `evaluation/results/round3.json`, `evaluation/round3_report.md`
- 상태: 진행 중. 끝나면 결과를 새 항목으로 덧붙임

### 7. 작업 기록 파일과 규칙 추가
- 요청: history.md를 만들어 채팅에서 진행한 작업을 순서대로 저장하고, 이 규칙을 CLAUDE.md에 적기
- 한 일: `history.md`를 만들어 1~7번을 기록함. `CLAUDE.md` "추가 규칙"에 history.md 기록 규칙을 추가함
  - AGENTS.md는 이 프로젝트에 없어서 CLAUDE.md에만 적음

### 8. 3차 평가 결과 (6번 완료)
- 결과: **19/20 통과**, 필수(guardrail 3건 + 9번) 4/4
  - 실패 1건: 17번 "톨루엔 관련해서 바뀐 규제 있어?". 'P-002는 톨루엔이 있지만 15번 화학물질관리법 표기가 없어 해당 없음' 안내가 빠짐. 2차에서는 17번이 통과하고 12번이 실패했음. 이번에 17번은 `find_products_by_cas`를 호출하지 않음
- RAGAS: faithfulness 0.81(목표 0.85, 2차 0.78), context_recall 0.93(2차 0.87), context_precision 0.89, answer_relevancy 0.56
- 응답 시간: 평균 9.4초, 15초 이내 17/20(2차 18/20)
- 결과 파일: `evaluation/results/round3.json`, `evaluation/round3_report.md`. 2차 보고서는 그대로 둠

### 9. faithfulness 개선 (4차 평가 진행 중)
- 요청: faithfulness가 목표(0.85)를 넘도록 개선
- 원인 분석(3차 결과): 답변 문장이 붙인 근거(contexts)로 뒷받침되지 않는 경우
  - 근거가 8개를 넘으면 RAGAS가 앞 8개만 봄. 14·16번은 답변과 무관한 제품 MSDS가 앞을 차지해 P-002 MSDS·규칙 판정·정책 근거가 잘림
  - 18번(영업비밀 거절): 답변의 공개 명칭·함유량 범위를 뒷받침하는 MSDS 근거가 없었음
  - 7번: 개정 초안에 근거에 없는 줄(GHS07, H317, 개정번호 Rev.5)을 LLM이 덧붙임
- 한 일 (기존 코드는 주석으로 남김)
  - `src/workflows/evidence_text.py`: `prune_contexts` 추가(답변에 나오지 않는 제품의 MSDS 근거 제외), 정책 근거에서 `**` 기호 제거
  - `src/workflows/graph.py`: `_response`에서 `prune_contexts` 적용, 영업비밀 거절 시 질문 속 제품의 MSDS 3번 항목(마스킹본)을 근거로 추가
  - `src/agents/prompts.py`: JUDGE_PROMPT의 draft 규칙에 '도구 결과에 없는 항목은 덧붙이지 않기' 추가
- 확인: 9·18번 거절 응답과 `prune_contexts` 동작을 직접 실행해 확인함(단위 테스트는 실행하지 않음)
- 평가 하네스(`evaluation/run_eval.py`)의 근거 8개 제한은 바꾸지 않음
- 상태: 4차 평가(`--round 4`) 진행 중. 실행 중인 서버는 아직 이전 코드라 재시작 필요

### 10. 4차 평가 결과 (9번 완료)
- 결과: **19/20 통과**, 필수 4/4. 실패는 3차와 같은 17번
- RAGAS: faithfulness **0.75**(3차 0.81 → 오히려 내려감, 목표 0.85 미달), context_recall 0.94, context_precision 0.89, answer_relevancy 0.54
- 응답 시간: 평균 9.0초
- 문항별 faithfulness(3차 → 4차): 18번 0.50 → 0.83(영업비밀 거절 근거 추가 효과), 8번 0.78 → 0.89, 13번 0.73 → 0.79 상승.
  12번 1.00 → 0.33, 16번 0.71 → 0.48, 17번 0.91 → 0.46, 19번 0.83 → 0.67 하락
- 하락 원인 분석
  - 12번: 답변 내용은 3차와 거의 같음. 답변에 '영업비밀'이 나와 정책 근거가 붙었을 뿐인데 점수가 크게 바뀜 → RAGAS 채점 자체의 편차가 큼
  - 16번: 답변이 P-001·P-003·P-005도 언급해서 `prune_contexts`가 근거를 빼지 못함. 근거 12개 중 앞 8개만 채점되어 P-002 MSDS·규칙 판정·정책 근거가 여전히 잘림
  - 17번: 이번에는 `find_products_by_cas`를 호출해 근거가 12개가 됨 → 마찬가지로 잘림
  - 9번(범위 밖 거절)은 0.20 그대로
- 결론: 이번 수정으로 개선된 문항도 있지만, 평균은 RAGAS 채점 편차와 '근거 8개 제한'에 크게 좌우됨. 목표 달성 못 함
- 결과 파일: `evaluation/results/round4.json`, `evaluation/round4_report.md`
- 기타: `data/regulation_updates.json`이 U-06 추가·삭제 과정에서 줄바꿈 문자(CRLF→LF)만 바뀌어 있어 커밋본으로 되돌림(내용 같음)

### 11. GitHub에 올림
- 요청: 4차 평가가 끝나면 GitHub에 올리기
- 한 일: 서버를 재시작해 고친 코드를 반영함. 9~10번 변경(코드 3개, CLAUDE.md, history.md, 3·4차 평가 결과)을 커밋해 `origin/master`에 push
- 제외: `checkpoints.sqlite`, `index/`, `.archify/`, MSDS 이력 파일(기존 규칙)

### 12. 4차 평가 작업 원복 (로컬만)
- 요청: 4차 평가한 것 원복. 범위는 '코드 + 4차 결과 모두', GitHub에는 반영하지 않음(사용자 선택)
- 한 일: `src/agents/prompts.py`, `src/workflows/evidence_text.py`, `src/workflows/graph.py`를 9번 수정 전(커밋 `c9e96f8`, 3차 평가 때) 상태로 되돌림. `evaluation/results/round4.json`, `evaluation/round4_report.md` 삭제. 서버 재시작
- 유지: `history.md`, `CLAUDE.md`, 3차 평가 결과
- 상태: 로컬에서만 되돌림. GitHub `origin/master`(`598b222`)에는 9번 수정 코드와 4차 결과가 그대로 남아 있음

### 13. 원복을 GitHub에 반영
- 요청: 12번 원복 내용을 GitHub에도 올리기
- 한 일: 12번 변경(코드 3개 원복, 4차 결과 삭제, history.md)을 새 커밋으로 `origin/master`에 push. 이전 커밋 `598b222`는 이력에 남음
