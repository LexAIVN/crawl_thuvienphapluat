"""Integration tests for LuatVietnamAuthHandler with mocked Playwright."""

from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from pathlib import Path

from src.crawler.luatvietnam_auth import LuatVietnamAuthHandler
from src.config import LuatVietnamConfig


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv("LUATVIETNAM_USER", "test@example.com")
    monkeypatch.setenv("LUATVIETNAM_PASSWORD", "testpass")
    return LuatVietnamConfig(
        auth_state_path=tmp_path / ".auth" / "luatvietnam_state.json",
        download_dir=tmp_path / "data" / "nghidinh",
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
def handler(config):
    return LuatVietnamAuthHandler(config)


def _make_mock_browser():
    """Create a mock browser with new_context that returns a mock context."""
    browser = AsyncMock()
    context = AsyncMock()
    context.storage_state = AsyncMock()

    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.url = "https://luatvietnam.vn/"
    page.close = AsyncMock()

    context.new_page = AsyncMock(return_value=page)
    browser.new_context = AsyncMock(return_value=context)

    return browser, context, page


class TestVerifySession:
    async def test_valid_session_no_login_indicators(self, handler):
        """If no login indicators are visible, session is valid."""
        handler._browser = AsyncMock()

        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.close = AsyncMock()

        # All login indicator locators return count=0
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=locator)

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        result = await handler._verify_session(context)

        assert result is True
        page.close.assert_called_once()

    async def test_expired_session_login_visible(self, handler):
        """If a login indicator is visible, session is expired."""
        handler._browser = AsyncMock()

        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.close = AsyncMock()

        # First locator returns visible login indicator
        visible_locator = AsyncMock()
        visible_locator.count = AsyncMock(return_value=1)
        visible_locator.first = AsyncMock()
        visible_locator.first.is_visible = AsyncMock(return_value=True)

        page.locator = MagicMock(return_value=visible_locator)

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        result = await handler._verify_session(context)

        assert result is False

    async def test_navigation_failure_returns_false(self, handler):
        """If navigation fails, session verification returns False."""
        handler._browser = AsyncMock()

        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("Network error"))
        page.close = AsyncMock()

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        result = await handler._verify_session(context)

        assert result is False
        page.close.assert_called_once()


class TestPerformLogin:
    async def test_login_success_saves_session(self, handler, config):
        """Successful login should save session state to auth_state_path."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser

        # form0 exists
        page.evaluate = AsyncMock(side_effect=[
            True,                    # form_exists check
            "submitted via jQuery",  # _LOGIN_JS execution
            True,                    # is_logged_in check (logout found)
        ])

        result = await handler._perform_login()

        assert result is context
        context.storage_state.assert_called_once_with(
            path=str(config.auth_state_path)
        )
        page.close.assert_called_once()

    async def test_login_form_missing_raises(self, handler):
        """If form0 is not in DOM, login should raise RuntimeError."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser

        # form0 does NOT exist
        page.evaluate = AsyncMock(return_value=False)

        with pytest.raises(RuntimeError, match="form0"):
            await handler._perform_login()

        context.close.assert_called_once()

    async def test_login_failure_raises_with_errors(self, handler):
        """If login fails and validation errors are present, raise with details."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser

        page.evaluate = AsyncMock(side_effect=[
            True,                    # form_exists
            "submitted via jQuery",  # _LOGIN_JS
            False,                   # is_logged_in → False
            ["Tài khoản không hợp lệ"],  # validation errors
        ])

        with pytest.raises(RuntimeError, match="Tài khoản không hợp lệ"):
            await handler._perform_login()

        context.close.assert_called_once()

    async def test_login_failure_no_errors_raises_generic(self, handler):
        """If login fails with no validation errors, raise generic message."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser

        page.evaluate = AsyncMock(side_effect=[
            True,                    # form_exists
            "submitted via jQuery",  # _LOGIN_JS
            False,                   # is_logged_in → False
            [],                      # no validation errors
        ])

        with pytest.raises(RuntimeError, match="not logged in after submit"):
            await handler._perform_login()

    async def test_login_navigation_failure_raises(self, handler):
        """If page.goto fails, login should raise RuntimeError."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser
        page.goto = AsyncMock(side_effect=Exception("Connection refused"))

        with pytest.raises(RuntimeError, match="Connection refused"):
            await handler._perform_login()

        context.close.assert_called_once()

    async def test_login_passes_credentials_to_js(self, handler):
        """The JS evaluate call should receive user and password from config."""
        browser, context, page = _make_mock_browser()
        handler._browser = browser

        page.evaluate = AsyncMock(side_effect=[
            True,                    # form_exists
            "submitted via jQuery",  # _LOGIN_JS
            True,                    # is_logged_in
        ])

        await handler._perform_login()

        # Second evaluate call is _LOGIN_JS with credentials
        js_call = page.evaluate.call_args_list[1]
        args_dict = js_call[0][1]  # positional arg after the JS string
        assert args_dict["user"] == "test@example.com"
        assert args_dict["password"] == "testpass"
