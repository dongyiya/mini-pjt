#!/usr/bin/env bash
# WSL Ubuntu(root) 에서 실행: 로컬 레지스트리 + 게시판 포탈 실행
# 사용: COOLIFY_TOKEN=... bash run-board.sh   (토큰은 /root/portal.env 에 저장해 두고 다음부터 생략 가능)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ -n "${COOLIFY_TOKEN:-}" ]; then
  umask 077; echo "COOLIFY_TOKEN=$COOLIFY_TOKEN" > /root/portal.env
fi
[ -f /root/portal.env ] || { echo "COOLIFY_TOKEN 이 필요합니다."; exit 1; }

# 1) 로컬 이미지 저장소 (Coolify 가 이미지를 가져가는 곳)
docker inspect portal-registry >/dev/null 2>&1 || \
  docker run -d --name portal-registry --restart unless-stopped -p 127.0.0.1:5000:5000 -v portal-registry:/var/lib/registry registry:2

# 2) 게시판 포탈
docker build -q -t app-portal-board "$HERE/board" >/dev/null
docker rm -f app-portal-board >/dev/null 2>&1 || true
docker run -d --name app-portal-board --restart unless-stopped \
  --network coolify \
  --env-file /root/portal.env \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portal-data:/data \
  -l traefik.enable=true \
  -l 'traefik.http.routers.portal-board.rule=Host(`portal.localhost`)' \
  -l traefik.http.routers.portal-board.entrypoints=http \
  -l traefik.http.services.portal-board.loadbalancer.server.port=8000 \
  -l traefik.docker.network=coolify \
  app-portal-board >/dev/null
echo "게시판 포탈 실행: http://portal.localhost"
