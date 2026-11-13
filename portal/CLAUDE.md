# CLAUDE.md — 사내 앱 포탈 (게시판형, 로컬 Coolify)

mini-pjt 저장소의 `portal/` 폴더를 받은 PC에서 Claude Code가 포탈을 설치·구동할 때 따르는 안내입니다.
사용자는 비개발자일 수 있습니다. 모든 응답은 한국어로 하고, 사용자가 직접 해야 하는 일(재시작·계정 생성·토큰 발급)은 단계별로 짧게 안내합니다.

## 구성

- **WSL2 Ubuntu** 안에 **Coolify**(셀프호스팅 배포 플랫폼)를 설치합니다. 관리 화면: http://localhost:8000
- **게시판 포탈**(`board/`): zip 업로드 → `docker build` → 로컬 레지스트리(`127.0.0.1:5000`) push → Coolify API로 배포. 주소: http://portal.localhost
- 올린 서비스 주소: `http://<주소이름>.localhost` (Coolify 프록시 Traefik 이 80번 포트에서 연결). `*.localhost` 는 Chrome·Edge 에서 열립니다(PowerShell `Invoke-WebRequest` 는 이름을 못 찾으므로 테스트는 `curl -H "Host: portal.localhost" http://127.0.0.1/` 로).

## 설치 순서 (Windows PC 기준)

Windows 에서 Ubuntu 명령은 `wsl -d Ubuntu -u root -- bash <스크립트 경로>` 로 실행합니다. Git Bash 에서 실행할 때는 경로 변환을 막기 위해 `MSYS_NO_PATHCONV=1` 을 붙이고, 스크립트 경로는 `/mnt/c/...` 형식으로 씁니다.

1. **가상화·WSL 확인**
   - `(Get-CimInstance Win32_ComputerSystem).HypervisorPresent` 가 `False` 면, 관리자 권한으로 `wsl --install --no-distribution` 과
     `dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart` 실행 → **사용자에게 PC 재시작을 요청**하고 멈춥니다.
   - BIOS 가상화(`(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled`)가 `False` 면 사용자에게 BIOS 설정을 안내합니다.
2. **Ubuntu 설치**: `wsl --install -d Ubuntu --no-launch`. root 로 바로 쓰므로 사용자 계정은 만들지 않아도 됩니다.
3. **WSL 이 꺼지지 않게 유지**: WSL 은 실행 중인 프로그램이 없으면 Ubuntu 를 끕니다(그러면 Coolify 도 꺼짐).
   Claude 세션에서는 `wsl -d Ubuntu -u root -- sleep infinity` 를 **백그라운드**로 실행해 둡니다. 사용자에게는 "`wsl -d Ubuntu` 창을 하나 열어 두세요"라고 안내합니다.
4. **Coolify 설치**: `wsl -d Ubuntu -u root -- bash /mnt/c/<mini-pjt 경로>/portal/install-coolify.sh`
   - 처음 실행에서 systemd 를 켰다고 나오면 `wsl --shutdown` 후 다시 실행합니다(3번의 유지 프로세스도 다시 띄움).
   - 끝나면 http://localhost:8000 이 200 으로 응답하는지 확인합니다.
5. **사용자 작업 (멈추고 요청)**
   - http://localhost:8000 에서 **설치 후 10분 안에** 관리자 계정 가입 (지나면 `docker restart coolify` 후 다시).
   - http://localhost:8000/settings/advanced 에서 **API Access** 켜기 → 저장.
   - http://localhost:8000/security/api-tokens 에서 권한 **root** 토큰 발급 → 채팅에 붙여 달라고 요청.
6. **포탈 실행**: 토큰을 Ubuntu 로 넘겨 `run-board.sh` 실행. 토큰에 `|` 가 있어 명령줄 인자로 넘기면 깨지므로 `WSLENV` 로 넘깁니다.
   ```bash
   export MSYS_NO_PATHCONV=1 COOLIFY_TOKEN='<토큰>' WSLENV=COOLIFY_TOKEN
   wsl.exe -d Ubuntu -u root -- bash /mnt/c/<mini-pjt 경로>/portal/run-board.sh
   ```
   토큰은 Ubuntu 의 `/root/portal.env`(권한 600)에 저장되어, 다음부터는 `COOLIFY_TOKEN` 없이 실행해도 됩니다. 저장소에는 절대 커밋하지 않습니다.
7. **확인**: `curl -s -H "Host: portal.localhost" http://127.0.0.1/api/posts` 가 `[]`(또는 글 목록)을 돌려주면 완료. 사용자에게 http://portal.localhost 를 안내합니다.

## 다시 켜기 (PC 재시작 후)

`wsl -d Ubuntu` 창만 열어 두면 Coolify·레지스트리·포탈은 `restart unless-stopped` 로 자동으로 다시 뜹니다. 안 뜨면 6번의 `run-board.sh` 를 다시 실행합니다.

## 포탈 코드 수정 후 반영

`board/` 를 고친 뒤 `run-board.sh` 를 다시 실행하면 이미지를 다시 빌드하고 컨테이너를 교체합니다(게시판 데이터는 `portal-data` 볼륨에 남음).

## 주의

- **로컬 테스트용**입니다. 로그인이 없고, 올라온 zip 안의 코드가 서버에서 그대로 실행됩니다. 외부에 공개하지 않습니다.
- 비밀값(AWS 키 등)은 게시판의 "비밀값" 칸으로만 넘기고, zip·이미지·저장소에 넣지 않습니다.
- 셸 스크립트는 LF 줄바꿈이어야 Ubuntu 에서 실행됩니다(`.gitattributes` 로 고정).
