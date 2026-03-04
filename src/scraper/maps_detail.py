from __future__ import annotations

import re
from datetime import datetime, timezone

from playwright.async_api import Page

from src.domain import BusinessRecord
from src.pipeline.normalize import clean_phone, clean_rating, clean_text, clean_web


async def _read_by_data_item(page: Page, item_id: str) -> str:
    loc = page.locator(f'button[data-item-id="{item_id}"], a[data-item-id="{item_id}"]')
    if await loc.count() == 0:
        return ""
    text = await loc.first.inner_text()
    return clean_text(text)


async def _extract_phone(page: Page) -> str:
    # Most stable selector family: data-item-id starts with "phone"
    phone_loc = page.locator('[data-item-id^="phone"]')
    if await phone_loc.count() > 0:
        raw = clean_text(await phone_loc.first.inner_text())
        phone = _extract_phone_like(raw)
        if phone:
            return phone
        aria = clean_text((await phone_loc.first.get_attribute("aria-label")) or "")
        phone = _extract_phone_like(aria)
        if phone:
            return phone

    # Language-dependent labels as fallback
    for sel in [
        'button[aria-label*="Teléfono"]',
        'button[aria-label*="Phone"]',
        'a[aria-label*="Teléfono"]',
        'a[aria-label*="Phone"]',
    ]:
        loc = page.locator(sel)
        if await loc.count() == 0:
            continue
        text = clean_text(await loc.first.inner_text())
        phone = _extract_phone_like(text)
        if phone:
            return phone
        aria = clean_text((await loc.first.get_attribute("aria-label")) or "")
        phone = _extract_phone_like(aria)
        if phone:
            return phone

    # Last-resort fallback: parse from HTML payload
    content = await page.content()
    match = re.search(r"(\+?\d[\d\s().-]{7,}\d)", content)
    if match:
        return clean_text(match.group(1))
    return ""


def _extract_phone_like(text: str) -> str:
    if not text:
        return ""
    candidate = text.split(":", 1)[-1] if ":" in text else text
    candidate = clean_text(candidate)
    match = re.search(r"(\+?\d[\d\s().-]{7,}\d)", candidate)
    if match:
        return clean_text(match.group(1))
    return ""


async def _extract_category(page: Page) -> str:
    cat_candidates = [
        "button[jsaction*='pane.rating.category']",
        "button.DkEaL",
        "div[aria-label*='Categoría']",
    ]
    for sel in cat_candidates:
        loc = page.locator(sel)
        if await loc.count() > 0:
            txt = clean_text(await loc.first.inner_text())
            if txt:
                return txt
    return ""


async def extract_business_record(page: Page, source_query: str) -> BusinessRecord:
    name = ""
    heading = page.locator("h1")
    if await heading.count() > 0:
        name = clean_text(await heading.first.inner_text())

    phone = await _extract_phone(page)
    address = await _read_by_data_item(page, "address")
    website = await _read_by_data_item(page, "authority")

    if not website:
        website_loc = page.locator('a[data-item-id="authority"]')
        if await website_loc.count() > 0:
            href = await website_loc.first.get_attribute("href")
            website = clean_text(href)

    rating = ""
    rating_loc = page.locator('div[role="img"][aria-label*="estrellas"]')
    if await rating_loc.count() > 0:
        aria = (await rating_loc.first.get_attribute("aria-label")) or ""
        parts = aria.split(" ")
        if parts:
            rating = clean_rating(parts[0])

    if not rating:
        rating_alt = page.locator("span[aria-hidden='true']")
        count = await rating_alt.count()
        for idx in range(min(count, 12)):
            txt = clean_text(await rating_alt.nth(idx).inner_text())
            maybe = clean_rating(txt)
            if maybe:
                rating = maybe
                break

    category = await _extract_category(page)
    maps_url = page.url

    return BusinessRecord(
        nombre=clean_text(name),
        telefono=clean_phone(phone),
        direccion=clean_text(address),
        web=clean_web(website),
        rating=clean_rating(rating),
        categoria=clean_text(category),
        source_query=source_query,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        maps_url=maps_url,
    )
