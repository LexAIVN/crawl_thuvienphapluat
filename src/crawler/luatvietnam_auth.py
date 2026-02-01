"""Authentication handler for luatvietnam.vn."""

from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Playwright,
)

from ..config import LuatVietnamConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Anti-bot: prevent Chromium from exposing automation flags
_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]

# Mimic a real desktop Chrome user-agent
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Mask navigator.webdriver so the site cannot detect Playwright
_INIT_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
)


class LuatVietnamAuthHandler:
    """Handle authentication and session management for luatvietnam.vn.

    luatvietnam.vn blocks headless browsers by default. This handler
    uses anti-detection flags, a spoofed user-agent, and navigator.webdriver
    masking to bypass the check.

    Login is performed by filling the hidden login form fields directly
    and triggering jQuery AJAX submit, since the login modal is not
    reliably visible in headless mode.
    """

    def __init__(self, config: LuatVietnamConfig):
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "LuatVietnamAuthHandler":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize playwright and browser with anti-detection flags."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
            args=_BROWSER_ARGS,
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

        Tries loading a persisted session first. Falls back to fresh login.

        Returns:
            Authenticated BrowserContext ready for scraping and downloads
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

        logger.info("Performing fresh login")
        self._context = await self._perform_login()
        return self._context

    async def _load_session(self, state_path: Path) -> BrowserContext:
        """Load browser context from saved state with anti-detection headers."""
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(
            storage_state=str(state_path),
            accept_downloads=True,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        await context.add_init_script(_INIT_SCRIPT)
        return context

    async def _verify_session(self, context: BrowserContext) -> bool:
        """Verify session by checking for login indicators on base_url.

        luatvietnam.vn shows a login link/modal when not authenticated.
        If login triggers are absent or hidden, the session is valid.

        Returns:
            True if session is valid, False otherwise
        """
        page = await context.new_page()
        try:
            await page.goto(
                self.config.base_url,
                timeout=self.config.page_timeout,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Check for visible login indicators
            login_indicators = [
                'a:has-text("Đăng nhập / Đăng ký")',
                'a:has-text("Đăng nhập")',
                'button:has-text("Đăng nhập")',
                'a[href*="login"]',
            ]
            for selector in login_indicators:
                try:
                    locator = page.locator(selector)
                    if await locator.count() > 0:
                        if await locator.first.is_visible():
                            return False
                except Exception:
                    continue

            return True
        except Exception as e:
            logger.error("Session verification failed", error=str(e))
            return False
        finally:
            await page.close()

    async def _perform_login(self) -> BrowserContext:
        """Perform login via direct form fill and jQuery AJAX submit.

        luatvietnam.vn uses a hidden login form (#form0) with fields
        #customer_name and #password_login. The form submits via jQuery
        unobtrusive AJAX to /Account/DoLogin. The login modal is not
        reliably visible in headless mode, so we fill and submit the
        form directly via JavaScript.

        Flow:
            1. Navigate to base_url (loads the login form in DOM)
            2. Fill #customer_name and #password_login via JS
            3. Trigger jQuery form submit
            4. Verify success by checking for logout reference in page
            5. Save session state

        Returns:
            Authenticated BrowserContext
        """
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(
            accept_downloads=True,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        await context.add_init_script(_INIT_SCRIPT)
        page = await context.new_page()

        try:
            logger.info("Navigating to login page", url=self.config.login_url)
            await page.goto(
                self.config.login_url,
                timeout=self.config.page_timeout,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Verify the login form exists in DOM
            form_exists = await page.evaluate(
                "() => !!document.getElementById('form0')"
            )
            if not form_exists:
                raise RuntimeError(
                    "Login form (form0) not found — site may have changed structure"
                )

            # Fill credentials and submit via jQuery AJAX
            result = await page.evaluate(
                _LOGIN_JS,
                {"user": self.config.user, "password": self.config.password.get_secret_value()},
            )
            logger.info("Form submitted", result=result)

            # Wait for AJAX response
            await page.wait_for_timeout(4000)

            # Verify login success: page should contain a logout reference
            is_logged_in = await page.evaluate(
                "() => document.body.innerHTML.toLowerCase().includes('logout')"
            )
            if not is_logged_in:
                # Check for validation errors
                errors = await page.evaluate("""
                    () => {
                        var els = document.querySelectorAll('.field-validation-error');
                        var msgs = [];
                        els.forEach(function(e) { if (e.textContent.trim()) msgs.push(e.textContent.trim()); });
                        return msgs;
                    }
                """)
                if errors:
                    raise RuntimeError(f"Login failed: {errors}")
                raise RuntimeError("Login failed: not logged in after submit")

            logger.info("Login successful")

            # Save session state
            self.config.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(self.config.auth_state_path))
            logger.info(
                "Session state saved", path=str(self.config.auth_state_path)
            )

            return context

        except Exception as e:
            await context.close()
            raise RuntimeError(f"Login failed: {e}") from e
        finally:
            await page.close()


# JavaScript that fills the login form and triggers jQuery AJAX submit.
# Passed as a string to page.evaluate() with {user, password} args.
_LOGIN_JS = """
(args) => {
    var nameField = document.getElementById('customer_name');
    var passField = document.getElementById('password_login');
    if (!nameField) return 'ERROR: customer_name not found';
    if (!passField) return 'ERROR: password_login not found';

    nameField.value = args.user;
    passField.value = args.password;

    nameField.dispatchEvent(new Event('input', { bubbles: true }));
    nameField.dispatchEvent(new Event('change', { bubbles: true }));
    passField.dispatchEvent(new Event('input', { bubbles: true }));
    passField.dispatchEvent(new Event('change', { bubbles: true }));

    var form = document.getElementById('form0');
    if (!form) return 'ERROR: form0 not found';

    if (typeof jQuery !== 'undefined') {
        jQuery(form).trigger('submit');
        return 'submitted via jQuery';
    }
    form.submit();
    return 'submitted directly';
}
"""
