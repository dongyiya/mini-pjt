#!/usr/bin/env bash
# WSL2 Ubuntu 안에서 실행: Coolify 설치 (로컬 테스트용)
# 사용: sudo bash install-coolify.sh
set -euo pipefail

# 1) systemd 확인 (Docker·Coolify 서비스에 필요). 꺼져 있으면 켜고 WSL 재시작 안내
if ! grep -q "systemd=true" /etc/wsl.conf 2>/dev/null; then
  printf "[boot]\nsystemd=true\n" >> /etc/wsl.conf
  echo "systemd 를 켰습니다. Windows PowerShell 에서 'wsl --shutdown' 후 이 스크립트를 다시 실행하세요."
  exit 0
fi

# 2) Coolify 공식 설치 스크립트 (Docker 도 함께 설치)
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash

echo "설치 완료: 브라우저에서 http://localhost:8000 을 열어 관리자 계정을 만드세요."
