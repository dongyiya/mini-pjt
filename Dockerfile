# (기존 코드)
# # TODO: 클린 환경 재현용 (선택사항)

# --- 새 코드: 클린 환경 재현용 이미지 ---
# 빌드: docker build -t msds-agent .
# 실행: docker run -p 8000:8000 --env-file ../.env msds-agent
#   - .env 는 상위 폴더(sds-ax-practice)에 있습니다. AWS Bedrock 키가 있어야 LLM·임베딩이 동작합니다.
#   - 검색 인덱스(index/)는 이미지에 넣지 않고, 컨테이너 시작 때 없으면 만듭니다(run.sh serve).
# 로컬 .venv 와 같은 Python 3.14 를 씁니다. 설치 문제가 생기면 로컬과 함께 버전을 바꿉니다.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY data ./data
COPY evaluation ./evaluation
COPY tests ./tests
COPY pytest.ini run.sh ./
RUN chmod +x run.sh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["./run.sh", "serve"]
