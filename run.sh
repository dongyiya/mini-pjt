#!/usr/bin/env bash
# (기존 코드)
# # 실행 스크립트 (선택)
# set -euo pipefail

# --- 새 코드: 실행 스크립트 ---
# 사용법: ./run.sh [setup|index|serve|test|eval1|eval2]
#   setup : 법령·물질 데이터 수집 + 검색 인덱스 생성
#   index : 검색 인덱스만 생성
#   serve : API 서버 실행 (인덱스가 없으면 먼저 생성) → http://localhost:8000/query
#   test  : 단위 테스트
#   eval1 / eval2 : 1차 / 2차 평가 보고서 생성
# 환경 변수는 상위 폴더 .env(로컬) 또는 docker --env-file 로 전달합니다.
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ../.venv/Scripts/python ]; then PY=../.venv/Scripts/python      # Windows 로컬 (Git Bash)
elif [ -x ../.venv/bin/python ]; then PY=../.venv/bin/python             # macOS/Linux 로컬
else PY=python; fi                                                       # Docker
export PYTHONIOENCODING=utf-8

case "${1:-serve}" in
  setup) $PY -m scripts.collect_data && $PY -m scripts.collect_substances && $PY -m scripts.build_index ;;
  index) $PY -m scripts.build_index ;;
  serve)
    [ -f index/vectors.npy ] || $PY -m scripts.build_index || echo "[경고] 인덱스 생성 실패 → BM25만으로 검색합니다."
    exec $PY -m uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
  test)  $PY -m pytest ;;
  eval1) $PY -m evaluation.run_eval --round 1 ;;
  eval2) $PY -m evaluation.run_eval --round 2 ;;
  *) echo "사용법: $0 [setup|index|serve|test|eval1|eval2]"; exit 1 ;;
esac
