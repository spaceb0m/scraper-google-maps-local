import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from src.scraper.maps_detail import extract_business_record


def test_extract_business_record_from_fixture() -> None:
    async def run() -> None:
        fixture = Path("tests/fixtures/maps_detail_sample.html").resolve()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"file://{fixture}")
            record = await extract_business_record(page, "tiendas de ropa en santiago")
            await browser.close()

        assert record.nombre == "Tienda Centro"
        assert record.telefono == "+34 981 00 00 00"
        assert "Rúa Nova" in record.direccion
        assert record.rating == "4.7"
        assert "ropa" in record.categoria.lower()

    asyncio.run(run())
