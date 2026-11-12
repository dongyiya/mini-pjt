"""설정을 한곳에서 읽습니다.

- 환경 변수는 상위 폴더(sds-ax-practice)의 `.env`에서 읽습니다. 프로젝트 안에 새 `.env`를 만들지 않습니다.
- 데이터·인덱스·체크포인트 경로, 모델 ID, 오늘 날짜(질문 기준일 기본값)를 제공합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # mini-pjt
ENV_PATH = ROOT.parent / ".env"                         # sds-ax-practice/.env
load_dotenv(ENV_PATH, override=False)

DATA_DIR = ROOT / "data"
LAW_DIR = DATA_DIR / "laws"
SUBSTANCE_DIR = DATA_DIR / "substances"
MSDS_PATH = DATA_DIR / "msds" / "products.json"
UPDATES_PATH = DATA_DIR / "regulation_updates.json"
INDEX_DIR = ROOT / "index"
CHECKPOINT_DB = ROOT / "checkpoints.sqlite"

DEFAULT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"


@dataclass(frozen=True)
class Settings:
    aws_region: str
    bedrock_model_id: str
    embed_model_id: str
    law_api_oc: str
    data_go_kr_key: str
    langsmith_project: str


def get_settings() -> Settings:
    """호출할 때마다 환경 변수를 다시 읽습니다(테스트에서 바꾸기 쉽도록)."""
    return Settings(
        aws_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        embed_model_id=os.getenv("BEDROCK_EMBED_MODEL_ID", DEFAULT_EMBED_MODEL),
        law_api_oc=os.getenv("LAW_API_OC", ""),
        data_go_kr_key=os.getenv("DATA_GO_KR_API_KEY", ""),
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "mini-pjt"),
    )


def today() -> date:
    """질문 기준일의 기본값. 환경 변수 MSDS_TODAY(YYYY-MM-DD)로 고정할 수 있습니다(평가 재현용)."""
    fixed = os.getenv("MSDS_TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()
