# 게시판형 포탈 서버 — docker CLI 가 들어 있는 이미지에 Python(FastAPI) 을 얹음
# 실행은 ../run-board.sh 참고 (docker.sock 마운트, coolify 네트워크, Traefik 라벨)
FROM docker:29-cli
RUN apk add --no-cache python3 py3-pip \
 && pip install --no-cache-dir --break-system-packages fastapi==0.115.* uvicorn==0.32.* python-multipart requests
WORKDIR /app
COPY app.py ./
COPY static ./static
ENV DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
