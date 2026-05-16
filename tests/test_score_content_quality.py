from scripts.score_content_quality import score_content


def test_empty_content_scores_low():
    score, error_type = score_content("Title", "<html></html>", "", 200)

    assert score < 0.4
    assert error_type == "empty_content"


def test_captcha_scores_low():
    score, error_type = score_content(
        "Checking", "<html>captcha</html>", "Verify you are human", 200
    )

    assert score < 0.4
    assert error_type == "captcha"


def test_normal_article_scores_good():
    text = "This is a useful article. " * 40
    html = f"<html><title>Article</title><main>{text}</main></html>"

    score, error_type = score_content("Article", html, text, 200)

    assert score >= 0.7
    assert error_type is None


def test_missing_title_reduces_score():
    text = "This is a useful article. " * 40
    html = f"<html><main>{text}</main></html>"

    score, _error_type = score_content("", html, text, 200)

    assert score == 0.8


def test_low_text_to_html_ratio_reduces_score():
    text = "Short but meaningful content. " * 25
    html = "<html>" + ("<nav>menu</nav>" * 2000) + f"<main>{text}</main></html>"

    score, _error_type = score_content("Title", html, text, 200)

    assert score <= 0.8


def test_nextjs_forbidden_undefined_payload_is_not_blocked():
    text = "ALPHAXXXX helps businesses improve AI search visibility. " * 20
    html = (
        "<html><main>"
        + text
        + '</main><script>{"forbidden":"$undefined","unauthorized":"$undefined"}</script></html>'
    )

    score, error_type = score_content("ALPHAXXXX", html, text, 200)

    assert score >= 0.7
    assert error_type is None


def test_article_mentioning_cloudflare_or_captcha_is_not_blocked():
    text = (
        "Agents are users and the Cloudflare Perplexity fight misses the point. "
        "The article discusses captcha challenges as a product and policy topic. "
    ) * 20
    html = f"<html><title>Cloudflare analysis</title><main>{text}</main></html>"

    score, error_type = score_content("Cloudflare analysis", html, text, 200)

    assert score >= 0.7
    assert error_type is None
