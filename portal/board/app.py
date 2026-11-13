"""사내 앱 포탈 (게시판형) — zip 업로드 → docker build → 로컬 레지스트리 push → Coolify 배포.

로컬 테스트용(WSL2 + Coolify). 로그인 없이 이름만 받고, 삭제는 올린 사람 이름이 같을 때만 허용합니다.
환경 변수:
  COOLIFY_API    Coolify API 주소 (기본 http://coolify:8080/api/v1, 같은 docker 네트워크)
  COOLIFY_TOKEN  Coolify API 토큰 (root)
  REGISTRY       이미지를 올릴 레지스트리 (기본 localhost:5000, 호스트 docker 기준)
  DOMAIN_SUFFIX  서비스 주소 접미사 (기본 localhost → http://<주소이름>.localhost)
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

DATA = Path(os.getenv("DATA_DIR", "/data"))
DB = DATA / "portal.sqlite"
BUILDS = DATA / "builds"
API = os.getenv("COOLIFY_API", "http://coolify:8080/api/v1")
TOKEN = os.getenv("COOLIFY_TOKEN", "")
REGISTRY = os.getenv("REGISTRY", "localhost:5000")
SUFFIX = os.getenv("DOMAIN_SUFFIX", "localhost")
MAX_ZIP = 200 * 1024 * 1024  # 200MB
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,29}$")
RESERVED = {"portal", "www", "coolify"}

app = FastAPI(title="사내 앱 포탈")
_lock = threading.Lock()


# ---------- DB ----------
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    BUILDS.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, author TEXT NOT NULL,
            description TEXT, port TEXT NOT NULL, status TEXT NOT NULL,
            app_uuid TEXT, log TEXT DEFAULT '', created_at TEXT NOT NULL)""")


def update(pid: int, **kw) -> None:
    sets = ", ".join(f"{k}=?" for k in kw)
    with _lock, db() as con:
        con.execute(f"UPDATE posts SET {sets} WHERE id=?", (*kw.values(), pid))


def append_log(pid: int, text: str) -> None:
    with _lock, db() as con:
        con.execute("UPDATE posts SET log = log || ? WHERE id=?", (text.rstrip() + "\n", pid))


def get_post(pid: int) -> dict:
    with db() as con:
        row = con.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "글을 찾을 수 없습니다.")
    return dict(row)


# ---------- Coolify ----------
def cf(method: str, path: str, **kw):
    r = requests.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Coolify {method} {path} → {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def coolify_target() -> tuple[str, str]:
    """포탈 전용 프로젝트(없으면 생성)와 localhost 서버 uuid."""
    server = next(s["uuid"] for s in cf("GET", "/servers") if s.get("is_coolify_host"))
    proj = next((p["uuid"] for p in cf("GET", "/projects") if p["name"] == "게시판 포탈"), None)
    if not proj:
        proj = cf("POST", "/projects", json={"name": "게시판 포탈", "description": "포탈 게시판에서 올린 서비스"})["uuid"]
    return proj, server


def parse_envs(text: str) -> list[tuple[str, str]]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
            out.append((k, v.strip().strip('"').strip("'")))
    return out


# ---------- 빌드·배포 (백그라운드) ----------
def run(cmd: list[str], pid: int, cwd: Path | None = None) -> None:
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    tail: list[str] = []
    for line in p.stdout:  # type: ignore[union-attr]
        tail.append(line)
        if len(tail) >= 20:
            append_log(pid, "".join(tail)); tail.clear()
    if tail:
        append_log(pid, "".join(tail))
    if p.wait() != 0:
        raise RuntimeError(f"명령 실패: {' '.join(cmd[:3])} ...")


def find_context(root: Path) -> Path:
    """압축 안에서 Dockerfile 이 있는 가장 얕은 폴더."""
    hits = sorted(root.rglob("Dockerfile"), key=lambda p: len(p.parts))
    if not hits:
        raise RuntimeError("zip 안에서 Dockerfile 을 찾지 못했습니다.")
    return hits[0].parent


def build_and_deploy(pid: int, envs: list[tuple[str, str]]) -> None:
    post = get_post(pid)
    slug, work = post["slug"], BUILDS / post["slug"]
    try:
        ctx = find_context(work / "src")
        tag = datetime.now().strftime("%Y%m%d%H%M%S")
        image = f"{REGISTRY}/{slug}"
        update(pid, status="빌드 중")
        append_log(pid, f"[포탈] docker build ({ctx.relative_to(work / 'src') or '.'}) → {image}:{tag}")
        run(["docker", "build", "-t", f"{image}:{tag}", "."], pid, cwd=ctx)
        run(["docker", "push", f"{image}:{tag}"], pid)

        update(pid, status="배포 중")
        proj, server = coolify_target()
        body = {"project_uuid": proj, "server_uuid": server, "environment_name": "production",
                "name": slug, "description": post["title"],
                "docker_registry_image_name": image, "docker_registry_image_tag": tag,
                "ports_exposes": post["port"], "domains": f"http://{slug}.{SUFFIX}", "instant_deploy": False}
        if post["app_uuid"]:
            uuid = post["app_uuid"]
            cf("PATCH", f"/applications/{uuid}", json={"docker_registry_image_tag": tag})
        else:
            uuid = cf("POST", "/applications/dockerimage", json=body)["uuid"]
            update(pid, app_uuid=uuid)
        for k, v in envs:
            cf("POST", f"/applications/{uuid}/envs", json={"key": k, "value": v, "is_preview": False})
        if envs:
            append_log(pid, f"[포탈] 비밀값 {len(envs)}개 등록: {', '.join(k for k, _ in envs)}")
        dep = cf("POST", "/deploy", json={"uuid": uuid})
        append_log(pid, f"[포탈] Coolify 배포 요청: {json.dumps(dep, ensure_ascii=False)[:200]}")
        update(pid, status="배포 중")
    except Exception as e:  # noqa: BLE001 — 실패 사유를 게시판에 보여 줌
        append_log(pid, f"[포탈] 실패: {e}")
        update(pid, status="실패")
    finally:
        shutil.rmtree(work / "src", ignore_errors=True)  # 빌드가 끝나면 압축 해제본 삭제(zip 은 보관)


def live_status(post: dict) -> str:
    """Coolify 실제 상태로 '배포 중/실행 중/중지됨' 갱신."""
    if post["status"] not in ("배포 중", "실행 중", "중지됨") or not post["app_uuid"]:
        return post["status"]
    try:
        s = cf("GET", f"/applications/{post['app_uuid']}").get("status", "")
    except Exception:  # noqa: BLE001
        return post["status"]
    new = "실행 중" if s.startswith("running") else ("배포 중" if post["status"] == "배포 중" and not s.startswith("exited:unhealthy") else "중지됨")
    if s.startswith("exited") and post["status"] == "배포 중":
        new = "배포 중"  # 첫 배포 직후 잠깐 exited 로 보일 수 있음
    if new != post["status"]:
        update(post["id"], status=new)
    return new


# ---------- API ----------
@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/posts")
def list_posts():
    with db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id,title,slug,author,status,app_uuid,created_at FROM posts ORDER BY id DESC")]
    for r in rows:
        r["status"] = live_status(r)
        r["url"] = f"http://{r['slug']}.{SUFFIX}"
        r.pop("app_uuid")
    return rows


@app.get("/api/posts/{pid}")
def post_detail(pid: int):
    p = get_post(pid)
    p["status"] = live_status(p)
    p["url"] = f"http://{p['slug']}.{SUFFIX}"
    p.pop("app_uuid")
    return p


@app.post("/api/posts")
async def create_post(title: str = Form(...), slug: str = Form(...), author: str = Form(...),
                      description: str = Form(""), port: str = Form("8000"), envs: str = Form(""),
                      file: UploadFile = File(...)):
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug) or slug in RESERVED:
        raise HTTPException(400, "주소 이름은 영문 소문자로 시작하고 영문 소문자·숫자·하이픈 2~30자여야 합니다.")
    if not port.isdigit():
        raise HTTPException(400, "포트는 숫자여야 합니다.")
    if not title.strip() or not author.strip():
        raise HTTPException(400, "서비스 이름과 올린 사람을 입력하세요.")
    data = await file.read()
    if len(data) > MAX_ZIP:
        raise HTTPException(400, "파일은 200MB 이하만 올릴 수 있습니다.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "zip 파일만 올릴 수 있습니다.")
    with db() as con:
        if con.execute("SELECT 1 FROM posts WHERE slug=?", (slug,)).fetchone():
            raise HTTPException(400, f"'{slug}' 주소는 이미 쓰고 있습니다.")
        cur = con.execute(
            "INSERT INTO posts(title,slug,author,description,port,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (title.strip(), slug, author.strip(), description.strip(), port, "업로드됨",
             datetime.now().strftime("%Y-%m-%d %H:%M")))
        pid = cur.lastrowid
    work = BUILDS / slug
    shutil.rmtree(work, ignore_errors=True)
    (work / "src").mkdir(parents=True)
    (work / "upload.zip").write_bytes(data)
    base = (work / "src").resolve()
    for m in zf.infolist():  # 경로 탈출(zip slip) 방지
        target = (base / m.filename).resolve()
        if not str(target).startswith(str(base)):
            continue
        zf.extract(m, base)
    append_log(pid, f"[포탈] 업로드 완료: {file.filename} ({len(data) // 1024} KB)")
    threading.Thread(target=build_and_deploy, args=(pid, parse_envs(envs)), daemon=True).start()
    return {"id": pid}


@app.post("/api/posts/{pid}/redeploy")
def redeploy(pid: int):
    p = get_post(pid)
    if not p["app_uuid"]:
        raise HTTPException(400, "아직 배포된 적이 없습니다.")
    cf("POST", "/deploy", json={"uuid": p["app_uuid"]})
    update(pid, status="배포 중")
    append_log(pid, "[포탈] 다시 배포 요청")
    return {"ok": True}


@app.delete("/api/posts/{pid}")
def delete_post(pid: int, author: str):
    p = get_post(pid)
    if author.strip() != p["author"]:
        raise HTTPException(403, "올린 사람 이름이 같아야 삭제할 수 있습니다.")
    if p["app_uuid"]:
        try:
            cf("DELETE", f"/applications/{p['app_uuid']}")
        except Exception:  # noqa: BLE001 — Coolify 쪽이 이미 없어도 글은 지움
            pass
    shutil.rmtree(BUILDS / p["slug"], ignore_errors=True)
    with _lock, db() as con:
        con.execute("DELETE FROM posts WHERE id=?", (pid,))
    return {"ok": True}
