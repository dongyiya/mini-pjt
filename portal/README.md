# 사내 앱 포탈 (게시판형)

Dockerfile이 들어 있는 소스 폴더를 **zip으로 올리면** 자동으로 빌드·배포되어 `http://<주소이름>.localhost` 로 서비스되는 게시판입니다.
배포는 PC 안(WSL2 Ubuntu)에 설치한 [Coolify](https://coolify.io)가 맡습니다. **로컬 테스트용**입니다.

## 화면

- **목록**: 번호 · 서비스 이름 · 올린 사람 · 상태(업로드됨 → 빌드 중 → 배포 중 → 실행 중 / 실패) · 주소 · 올린 날짜
- **새 서비스 올리기**: 서비스 이름, 올린 사람, 주소 이름(영문), 포트, 설명, zip 파일, 비밀값(`KEY=VALUE`)
- **상세**: 빌드 로그(자동 새로고침), 서비스 열기, 다시 배포, 삭제(올린 사람 이름이 같을 때만)

## 다른 PC에서 설치하기

가장 쉬운 방법은 mini-pjt 저장소를 받아 `portal` 폴더에서 **Claude Code를 열고 "포탈 설치해줘"라고 하는 것**입니다.
Claude Code가 [CLAUDE.md](CLAUDE.md)의 순서대로 설치하고, 사람이 해야 하는 일(PC 재시작, Coolify 관리자 가입, API 토큰 발급)만 안내합니다.

직접 하려면 [CLAUDE.md](CLAUDE.md)의 "설치 순서"를 따라 하세요. 필요한 것:

- Windows 10/11 (BIOS 가상화 켜짐), 메모리 8GB 이상 권장
- 관리자 권한 (WSL 설치), 인터넷 연결

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `board/app.py` | 게시판 서버(FastAPI): 업로드 → `docker build` → 로컬 레지스트리 push → Coolify API 배포 |
| `board/static/index.html` | 게시판 화면(목록·글쓰기·상세) |
| `board/Dockerfile` | 포탈 서버 이미지 |
| `install-coolify.sh` | Ubuntu 안에서 Coolify 설치 |
| `run-board.sh` | 로컬 레지스트리 + 포탈 실행 (Ubuntu 안에서) |
| `index.html`, `Dockerfile` | 처음 만든 정적 소개 페이지 (참고용, 사용 안 함) |

## 주소

| 주소 | 내용 |
| --- | --- |
| http://localhost:8000 | Coolify 관리 화면 |
| http://portal.localhost | 게시판 포탈 |
| http://<주소이름>.localhost | 게시판에서 올린 서비스 |

`*.localhost` 주소는 Chrome·Edge에서 열립니다.

## 주의

- 로그인이 없고, 올라온 zip 안의 코드가 PC에서 그대로 실행됩니다. **외부에 공개하지 마세요.**
- AWS 키 같은 비밀값은 zip에 넣지 말고 "비밀값" 칸에 입력하세요.
