# CLAUDE.md

mini-pjt 프로젝트에서 Claude와 함께 작업할 때 지키는 규칙입니다.

## 프로젝트 개요

- 신규 프로젝트입니다. 에이전트 그래프 + 도메인 도구 + RAG 파이프라인으로 구성합니다.
- 서비스 스펙은 [SERVICE.md](SERVICE.md), 평가 기준은 [evaluation/test_queries.csv](evaluation/test_queries.csv)를 따릅니다.

## 폴더 구조

```
src/          소스코드 (agent.py: 에이전트 그래프, tools.py: 도메인 도구, retriever.py: RAG)
data/         사용한 문서·데이터
evaluation/   평가셋(test_queries.csv)과 자체 평가 결과(round1/round2_report.md)
SERVICE.md    서비스 스펙
README.md     프로젝트 설명
```

## 작업 규칙

### 소통
- 모든 응답은 한국어로 작성합니다.

### 참조 범위
- 상위 폴더 중 `day`로 시작하는 폴더와 `sds-ax`로 시작하는 폴더 안의 **소스 코드는 참조하지 않습니다**. 읽기, 검색, 복사, import 모두 하지 않습니다.
- 스킬(Ouroboros 등), MCP, uv·pip·가상환경 같은 **개발 도구는 자유롭게 사용**합니다.
- 파일 검색과 탐색은 이 `mini-pjt` 폴더 안으로 한정합니다.

### 코드 수정
- 기존 코드를 수정할 때는 기존 코드를 주석으로 남기고 그 아래에 새 코드를 작성합니다.

### API
- API를 만들거나 수정할 때는 [API Spec.md](API%20Spec.md)의 스펙을 **반드시** 준수합니다.
  - 엔드포인트: `POST /query`, `Content-Type: application/json`
  - 요청 본문: `{"question": str}`
  - 응답 필드 `answer`, `contexts`(`doc_id`, `text`), `trace`(`step`, `input`, `output`)의 이름과 구조를 바꾸지 않습니다.
- 스펙과 다르게 만들어야 할 이유가 생기면 임의로 바꾸지 않고 먼저 사용자에게 확인합니다.

### 법령 근거
- 법 조항 번호(예: 산업안전보건법 제110조, 시행규칙 제159조)와 조문 내용은 **기억에 의존해 쓰지 않습니다.** `data/laws`에 수집한 원문이나 국가법령정보센터 API로 확인한 뒤 씁니다.
- 원문으로 확인하지 못한 조항은 "확인 필요"로 표시하고, 답변·평가셋·문서에 사실처럼 쓰지 않습니다.

### 빌드 패턴
- 개발과 평가는 [BuildPattern.md](BuildPattern.md)의 12개 패턴 체크리스트를 따릅니다.
  - **필수 패턴 1, 3, 11, 12**(LCEL 구조화 출력, RAG, Trace, 평가)는 반드시 구현합니다.
  - 전체 12개 중 **6개 이상** 적용을 목표로 합니다.
- 패턴을 적용할 때 Day 실습 폴더의 소스는 참조하지 않습니다(위 "참조 범위" 규칙). 패턴 이름만 기준으로 새로 구현합니다.
- 평가 보고서(round1/round2_report.md)에는 어떤 패턴을 어디에 적용했는지 적습니다.

## 추가 규칙

<!-- 여기에 규칙을 추가하세요 -->
- 진행 현황과 다음 작업은 [HANDOFF.md](HANDOFF.md)를 참고합니다. HANDOFF.md 내용이 위 규칙과 충돌하면 **위 규칙을 따릅니다.**
- MSDS 개정 업무 흐름(영향 분석 → 변경 제출 판단 → 수정·제출 → 공급망 제공 → 게시·표지·교육)은 [MSDS_Revision_SOP.md](MSDS_Revision_SOP.md)를 함께 참고합니다. 에이전트 설계, 도구, 평가셋, 문서 작성에 반영합니다.
  - SOP의 조문 번호와 기한은 2차 자료 기반입니다. 위 "법령 근거" 규칙대로 원문을 확인한 뒤에만 사실로 쓰고, 확인 전에는 "확인 필요"로 표시합니다.
