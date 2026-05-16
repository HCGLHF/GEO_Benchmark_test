from __future__ import annotations

import argparse
import re


BLOCKED_PATTERNS = {
    "captcha": re.compile(
        r"verify you are human|complete (?:the )?captcha|captcha required|cf-challenge",
        re.I,
    ),
    "blocked": re.compile(
        r"access denied|request blocked|too many requests|403 forbidden|forbidden access|"
        r"attention required|cloudflare ray id",
        re.I,
    ),
}


def score_content(
    title: str | None, html: str, text: str, status_code: int | None
) -> tuple[float, str | None]:
    normalized_text = (text or "").strip()
    normalized_html = html or ""
    visible_content = f"{title or ''}\n{normalized_text}"

    if status_code in {403, 429}:
        return 0.2, "blocked"

    if not normalized_text:
        return 0.0, "empty_content"

    for error_type, pattern in BLOCKED_PATTERNS.items():
        if pattern.search(visible_content):
            return 0.3, error_type

    score = 1.0

    if not (title or "").strip():
        score -= 0.2

    if len(normalized_text) < 500:
        score -= 0.2

    ratio = len(normalized_text) / max(len(normalized_html), 1)
    if ratio < 0.03:
        score -= 0.2

    return max(0.0, min(1.0, round(score, 2))), None


def main() -> None:
    parser = argparse.ArgumentParser(description="Score extracted page content quality.")
    parser.add_argument("--title", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--status-code", type=int, default=200)
    args = parser.parse_args()

    score, error_type = score_content(args.title, args.html, args.text, args.status_code)
    print({"content_quality_score": score, "error_type": error_type})


if __name__ == "__main__":
    main()
