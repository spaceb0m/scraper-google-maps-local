from src.analyzer.fingerprint import detect_platform

SHOPIFY_HTML = '<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>'
WOOCOMMERCE_HTML = '<link rel="stylesheet" href="/wp-content/plugins/woocommerce/assets/css/woocommerce.css">'
PRESTASHOP_HTML = '<script>var prestashop = {};</script>'
MAGENTO_HTML = '<script type="text/x-magento-init">{"*":{"mage/cookies":{}}}</script>'
SQUARESPACE_HTML = '<link href="https://static.squarespace.com/universal/styles.css">'
WIX_HTML = '<link href="https://static.wixstatic.com/frog/main.css">'
WEBFLOW_HTML = '<script src="https://uploads-ssl.webflow.com/main.js">'
GENERIC_STORE_HTML = '<button class="add-to-cart">Añadir al carrito</button>'
GENERIC_CHECKOUT_HTML = '<a href="/checkout">Checkout</a>'
PLAIN_HTML = '<html><body><p>Bienvenido a nuestra web corporativa</p></body></html>'


def test_detect_shopify():
    is_store, platform = detect_platform(SHOPIFY_HTML)
    assert is_store is True
    assert platform == "Shopify"


def test_detect_woocommerce():
    is_store, platform = detect_platform(WOOCOMMERCE_HTML)
    assert is_store is True
    assert platform == "WooCommerce"


def test_detect_prestashop():
    is_store, platform = detect_platform(PRESTASHOP_HTML)
    assert is_store is True
    assert platform == "PrestaShop"


def test_detect_magento():
    is_store, platform = detect_platform(MAGENTO_HTML)
    assert is_store is True
    assert platform == "Magento"


def test_detect_squarespace():
    is_store, platform = detect_platform(SQUARESPACE_HTML)
    assert is_store is True
    assert platform == "Squarespace"


def test_detect_wix():
    is_store, platform = detect_platform(WIX_HTML)
    assert is_store is True
    assert platform == "Wix"


def test_detect_webflow():
    is_store, platform = detect_platform(WEBFLOW_HTML)
    assert is_store is True
    assert platform == "Webflow"


def test_detect_generic_store_add_to_cart():
    is_store, platform = detect_platform(GENERIC_STORE_HTML)
    assert is_store is True
    assert platform == "Desconocida"


def test_detect_generic_store_checkout():
    is_store, platform = detect_platform(GENERIC_CHECKOUT_HTML)
    assert is_store is True
    assert platform == "Desconocida"


def test_not_a_store():
    is_store, platform = detect_platform(PLAIN_HTML)
    assert is_store is False
    assert platform is None
