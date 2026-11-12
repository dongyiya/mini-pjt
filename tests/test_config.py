from datetime import date

from src import config


def test_paths_point_inside_project():
    assert config.ROOT.name == "mini-pjt"
    assert config.ENV_PATH.parent == config.ROOT.parent
    assert config.MSDS_PATH.exists()
    assert config.UPDATES_PATH.exists()


def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    s = config.get_settings()
    assert s.bedrock_model_id == "test-model"
    assert s.aws_region == "ap-northeast-2"
    assert s.embed_model_id == config.DEFAULT_EMBED_MODEL


def test_settings_defaults(monkeypatch):
    for k in ("BEDROCK_MODEL_ID", "AWS_DEFAULT_REGION", "BEDROCK_EMBED_MODEL_ID"):
        monkeypatch.delenv(k, raising=False)
    s = config.get_settings()
    assert s.aws_region == "us-east-1"
    assert s.bedrock_model_id.startswith("us.anthropic.")


def test_today_can_be_fixed(monkeypatch):
    monkeypatch.setenv("MSDS_TODAY", "2027-05-01")
    assert config.today() == date(2027, 5, 1)
    monkeypatch.delenv("MSDS_TODAY")
    assert config.today() == date.today()
