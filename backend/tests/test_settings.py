"""Configuration must be cwd-independent, overridable, and safe to represent."""

import importlib.util
import shutil

import pytest
from pydantic import ValidationError

from backend.app import settings as settings_module
from backend.app.settings import Settings


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_default_env_path_and_runtime_precedence_from_another_cwd(tmp_path, monkeypatch):
    module_path = tmp_path / "backend" / "app" / "settings.py"
    module_path.parent.mkdir(parents=True)
    shutil.copyfile(settings_module.__file__, module_path)
    (module_path.parents[1] / ".env").write_text("DEFAULT_LOCALE=ru\n", encoding="utf-8")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    spec = importlib.util.spec_from_file_location("isolated_settings", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Settings().default_locale == "ru"
    monkeypatch.setenv("DEFAULT_LOCALE", "en")
    assert module.Settings().default_locale == "en"


def test_env_example_loads_without_secrets():
    settings = Settings(_env_file=settings_module.BACKEND_ENV_PATH.with_name(".env.example"))
    assert settings.default_locale == "kk"
    assert not settings.twogis_enabled
    assert settings.openai_embedding_dimensions == 1536
    assert not settings.openai_api_key.get_secret_value()
    assert not settings.database_url.get_secret_value()


def test_embedding_dimensions_parse_env_and_are_fixed(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "1536")
    assert Settings(_env_file=None).openai_embedding_dimensions == 1536
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "3072")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_values_are_not_in_repr_or_json():
    settings = Settings(_env_file=None, openai_api_key="synthetic-secret-not-real")
    assert "synthetic-secret-not-real" not in repr(settings)
    assert "synthetic-secret-not-real" not in settings.model_dump_json()
