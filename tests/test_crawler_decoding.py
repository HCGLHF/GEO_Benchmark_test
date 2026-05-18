from scripts.crawl_pages import decode_response_text


class FakeResponse:
    def __init__(self, content: bytes, encoding: str | None) -> None:
        self.content = content
        self.encoding = encoding


def test_decode_response_text_prefers_valid_utf8_over_latin1_header():
    response = FakeResponse("Generative Engine Optimization – AI visibility".encode("utf-8"), "iso-8859-1")

    assert decode_response_text(response) == "Generative Engine Optimization – AI visibility"


def test_decode_response_text_uses_declared_encoding_when_utf8_is_invalid():
    response = FakeResponse("café".encode("cp1252"), "windows-1252")

    assert decode_response_text(response) == "café"
