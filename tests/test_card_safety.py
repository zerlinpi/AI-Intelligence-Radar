from app.cards import builders


def test_safe_http_url_accepts_http_and_https():
    assert builders._safe_http_url("https://example.com/a") == "https://example.com/a"
    assert builders._safe_http_url("http://example.com/b") == "http://example.com/b"


def test_safe_http_url_rejects_unsafe_or_malformed_links():
    assert builders._safe_http_url("javascript:alert(1)") == ""
    assert builders._safe_http_url("file:///etc/passwd") == ""
    assert builders._safe_http_url("example.com/no-scheme") == ""
    assert builders._safe_http_url("") == ""


def test_invalid_project_url_does_not_create_button():
    assert builders._button("查看项目", "javascript:alert(1)") is None
