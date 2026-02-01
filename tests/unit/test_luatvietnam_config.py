"""Unit tests for LuatVietnamConfig."""

import pytest
from pathlib import Path

from src.config import LuatVietnamConfig


class TestLuatVietnamConfig:
    def test_loads_from_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig()

        assert config.user == "user@test.com"
        assert config.password.get_secret_value() == "secret123"

    def test_missing_user_raises(self, monkeypatch, tmp_path):
        # Use empty env file to prevent .env on disk from supplying values
        empty_env = tmp_path / ".env.empty"
        empty_env.write_text("")
        monkeypatch.delenv("LUATVIETNAM_USER", raising=False)
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        with pytest.raises(Exception):
            LuatVietnamConfig(_env_file=str(empty_env))

    def test_missing_password_raises(self, monkeypatch, tmp_path):
        empty_env = tmp_path / ".env.empty"
        empty_env.write_text("")
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.delenv("LUATVIETNAM_PASSWORD", raising=False)

        with pytest.raises(Exception):
            LuatVietnamConfig(_env_file=str(empty_env))

    def test_default_download_dir(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig()
        assert config.download_dir == Path("data/nghidinh")

    def test_default_auth_state_path(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig()
        assert config.auth_state_path == Path(".auth/luatvietnam_state.json")

    def test_default_base_url(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig()
        assert config.base_url == "https://luatvietnam.vn"

    def test_default_search_url_contains_keywords(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig()
        assert "lDocTypeId=11" in config.search_url
        assert "lEffectStatusId=4" in config.search_url
        assert "tim-van-ban.html" in config.search_url

    def test_ensure_directories_creates_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")

        config = LuatVietnamConfig(
            download_dir=tmp_path / "nghidinh",
            auth_state_path=tmp_path / ".auth" / "luatvietnam_state.json",
            log_dir=tmp_path / "logs",
        )
        config.ensure_directories()

        assert (tmp_path / "nghidinh").is_dir()
        assert (tmp_path / ".auth").is_dir()
        assert (tmp_path / "logs").is_dir()

    def test_override_via_env(self, monkeypatch):
        monkeypatch.setenv("LUATVIETNAM_USER", "user@test.com")
        monkeypatch.setenv("LUATVIETNAM_PASSWORD", "secret123")
        monkeypatch.setenv("LUATVIETNAM_MAX_CONCURRENT", "5")
        monkeypatch.setenv("LUATVIETNAM_HEADLESS", "False")

        config = LuatVietnamConfig()
        assert config.max_concurrent == 5
        assert config.headless is False
