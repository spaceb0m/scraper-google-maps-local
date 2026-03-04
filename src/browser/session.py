from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


@dataclass
class BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


async def start_session(headless: bool, timeout_ms: int) -> BrowserSession:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    context = await browser.new_context(
        locale="es-ES",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    page.set_default_timeout(timeout_ms)
    return BrowserSession(
        playwright=pw,
        browser=browser,
        context=context,
        page=page,
    )


async def stop_session(session: BrowserSession) -> None:
    await session.context.close()
    await session.browser.close()
    await session.playwright.stop()
