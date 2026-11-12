import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# (추가 2026-11-12) 승인 → MSDS 반영(시험 기능)이 생긴 뒤로 승인 테스트가 실제 data/msds/products.json 에 씁니다.
# 테스트마다 제품 MSDS·개정 이력·반영 기록을 테스트 전 상태로 되돌려 실제 데이터가 바뀌지 않게 합니다.
@pytest.fixture(autouse=True)
def _protect_msds_data():
    from src.revision import msds_apply as M

    msds_before = M.MSDS_PATH.read_bytes()
    log_before = M.LOG_PATH.read_bytes() if M.LOG_PATH.exists() else None
    hist_before = set(M.HISTORY_DIR.rglob("*")) if M.HISTORY_DIR.exists() else None
    yield
    if M.MSDS_PATH.read_bytes() != msds_before:
        M.MSDS_PATH.write_bytes(msds_before)
    if log_before is None:
        M.LOG_PATH.unlink(missing_ok=True)
    elif M.LOG_PATH.read_bytes() != log_before:
        M.LOG_PATH.write_bytes(log_before)
    if M.HISTORY_DIR.exists():
        if hist_before is None:
            import shutil
            shutil.rmtree(M.HISTORY_DIR, ignore_errors=True)
        else:
            for p in sorted(set(M.HISTORY_DIR.rglob("*")) - hist_before, reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
