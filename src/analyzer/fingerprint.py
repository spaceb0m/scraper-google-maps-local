from __future__ import annotations

import logging
from typing import Optional, Tuple

LOGGER = logging.getLogger(__name__)

# Platform fingerprints: list of (platform_name, signature_substring)
_PLATFORMS = [
    ("Shopify",      "cdn.shopify.com"),
    ("WooCommerce",  "woocommerce"),
    ("PrestaShop",   "prestashop"),
    ("Magento",      "mage/"),
    ("Magento",      "Magento"),
    ("Squarespace",  "static.squarespace.com"),
    ("Wix",          "static.wixstatic.com"),
    ("Webflow",      "webflow.com"),
]

# Generic ecommerce indicators (case-insensitive)
_STORE_INDICATORS = [
    "add-to-cart",
    "addtocart",
    "/checkout",
    "/cart",
    "/carrito",
    "añadir al carrito",
    "agregar al carrito",
    "data-product-id",
]

# Domains considered "social" (not a real website)
_SOCIAL_DOMAINS = ("instagram.com", "facebook.com", "fb.com")


def is_social_url(url: str) -> bool:
    """Devuelve True si la URL es de una red social (no se analiza)."""
    return any(d in url.lower() for d in _SOCIAL_DOMAINS)


def detect_platform(html: str) -> Tuple[bool, Optional[str]]:
    """Analiza HTML para determinar si es tienda online y qué plataforma usa.

    Returns:
        (is_store, platform) where platform is None if not a store,
        the platform name if known, or "Desconocida" if store but unknown platform.
    """
    for platform_name, signature in _PLATFORMS:
        if signature in html:
            return (True, platform_name)

    html_lower = html.lower()
    for indicator in _STORE_INDICATORS:
        if indicator in html_lower:
            return (True, "Desconocida")

    return (False, None)


async def fetch_page(url: str, timeout_s: int = 10) -> Optional[str]:
    """Descarga el HTML de una URL. Devuelve None en caso de error."""
    import aiohttp
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GoogleMaps-Scraper-Analyzer/1.0)"}
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url, allow_redirects=True, ssl=False) as resp:
                if resp.status >= 400:
                    LOGGER.warning("HTTP %d para %s", resp.status, url)
                    return None
                return await resp.text(errors="replace")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Error fetching %s: %s", url, exc)
        return None
