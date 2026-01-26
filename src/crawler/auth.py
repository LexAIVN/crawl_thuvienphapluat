"""Authentication handler for thuvienphapluat.vn."""

from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Playwright,
)

from ..config import CrawlerConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class AuthHandler:
    """Handle authentication and session management."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "AuthHandler":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize playwright and browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )

    async def close(self) -> None:
        """Close browser and playwright."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def get_authenticated_context(self) -> BrowserContext:
        """Get or create an authenticated browser context.

        Returns:
            Authenticated BrowserContext ready for downloads
        """
        if self._context:
            return self._context

        state_path = self.config.auth_state_path

        if state_path.exists():
            logger.info("Loading existing session state", path=str(state_path))
            try:
                self._context = await self._load_session(state_path)
                if await self._verify_session(self._context):
                    logger.info("Session is valid, reusing")
                    return self._context
                else:
                    logger.warning("Session expired, re-authenticating")
                    await self._context.close()
                    self._context = None
            except Exception as e:
                logger.error("Failed to load session", error=str(e))

        # Perform fresh login
        logger.info("Performing fresh login")
        self._context = await self._perform_login()
        return self._context

    async def _load_session(self, state_path: Path) -> BrowserContext:
        """Load browser context from saved state."""
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        return await self._browser.new_context(
            storage_state=str(state_path),
            accept_downloads=True,
        )

    async def _verify_session(self, context: BrowserContext) -> bool:
        """Verify if the session is still valid.

        Returns:
            True if session is valid, False otherwise
        """
        page = await context.new_page()
        try:
            await page.goto(self.config.base_url, timeout=self.config.page_timeout)
            await page.wait_for_load_state("networkidle")

            # Check if we're still logged in by looking for user-specific elements
            # or checking for login button absence
            login_button = page.locator('a[href*="login.aspx"]')
            is_logged_out = await login_button.count() > 0

            return not is_logged_out
        except Exception as e:
            logger.error("Session verification failed", error=str(e))
            return False
        finally:
            await page.close()

    async def _perform_login(self) -> BrowserContext:
        """Perform login and save session state.

        Returns:
            Authenticated BrowserContext
        """
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # Navigate to login page
            logger.info("Navigating to login page", url=self.config.login_url)
            await page.goto(self.config.login_url, timeout=self.config.page_timeout)
            await page.wait_for_load_state("networkidle")

            # Fill in credentials
            logger.info("Filling login credentials")

            # Try multiple selectors for username field
            username_selectors = [
                '#UserName',
                'input[id="UserName"]',
                'input[placeholder*="Tên đăng nhập"]',
                'input[name="txtUsername"]',
                'input[type="text"][placeholder*="Tên"]',
            ]

            username_filled = False
            for selector in username_selectors:
                try:
                    username_input = page.locator(selector)
                    if await username_input.count() > 0:
                        await username_input.fill(self.config.username)
                        username_filled = True
                        logger.debug("Username filled", selector=selector)
                        break
                except Exception:
                    continue

            if not username_filled:
                raise RuntimeError("Could not find username input field")

            # Try multiple selectors for password field
            password_selectors = [
                '#Password',
                'input[id="Password"]',
                'input[type="password"][placeholder*="Mật khẩu"]',
                'input[type="password"]',
            ]

            password_filled = False
            for selector in password_selectors:
                try:
                    password_input = page.locator(selector)
                    if await password_input.count() > 0:
                        await password_input.fill(
                            self.config.password.get_secret_value()
                        )
                        password_filled = True
                        logger.debug("Password filled", selector=selector)
                        break
                except Exception:
                    continue

            if not password_filled:
                raise RuntimeError("Could not find password input field")

            # Click login button
            login_button_selectors = [
                '#Button1',
                'input[id="Button1"]',
                'input[value="Đăng nhập"]',
                'input[type="button"][value*="Đăng nhập"]',
                'input[type="submit"]',
            ]

            for selector in login_button_selectors:
                try:
                    button = page.locator(selector)
                    if await button.count() > 0:
                        await button.click()
                        logger.debug("Login button clicked", selector=selector)
                        break
                except Exception:
                    continue

            # Wait for navigation after login
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)  # Extra wait for redirects

            # Verify login success
            current_url = page.url
            if "login.aspx" in current_url:
                # Check for error messages
                error_selectors = [
                    ".error-message",
                    ".alert-danger",
                    'span[id*="Error"]',
                ]
                for selector in error_selectors:
                    error = page.locator(selector)
                    if await error.count() > 0:
                        error_text = await error.text_content()
                        raise RuntimeError(f"Login failed: {error_text}")
                raise RuntimeError("Login failed: still on login page")

            logger.info("Login successful", redirect_url=current_url)

            # Save session state
            self.config.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(self.config.auth_state_path))
            logger.info("Session state saved", path=str(self.config.auth_state_path))

            return context

        except Exception as e:
            await context.close()
            raise RuntimeError(f"Login failed: {e}") from e
        finally:
            await page.close()
