from src.pipeline.normalize import clean_rating, clean_text


def test_clean_text_collapses_spaces() -> None:
    assert clean_text("  hola   mundo  ") == "hola mundo"


def test_clean_rating_accepts_comma() -> None:
    assert clean_rating("4,6") == "4.6"


def test_clean_rating_invalid_returns_empty() -> None:
    assert clean_rating("n/a") == ""
