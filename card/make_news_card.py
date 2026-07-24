#!/usr/bin/env python3
"""Render an ITニュース card PNG from a JSON spec.

Usage: python3 make_news_card.py spec.json output.png

Spec fields:
  headline   - short punchy headline; wrap <span class="hi">..</span> to
               highlight a phrase in amber (optional). Keep to ~2 lines.
  chips      - optional list of short stat strings, e.g. ["621件の脆弱性",
               "CVSS 9.9"]. Rendered as amber pills. Omit or [] for none.
  body       - 1-2 sentence plain-language summary for beginners.
  source     - e.g. "(出典: トレンドマイクロ)"
  head_size  - optional headline font px (default 52; use 46 for long ones)

Requires playwright + chromium and Noto Sans CJK JP fonts.
"""
import html as _html
import json
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    with open(os.path.join(HERE, "news_template.html"), encoding="utf-8") as f:
        tmpl = f.read()

    chips = spec.get("chips") or []
    chips_html = "".join(f'<span class="chip">{_html.escape(c)}</span>' for c in chips)

    out = (
        tmpl.replace("__HEAD_SIZE__", str(spec.get("head_size", 52)))
        .replace("__HEADLINE__", spec["headline"])
        .replace("__CHIPS__", chips_html)
        .replace("__BODY__", spec.get("body", ""))
        .replace("__SOURCE__", _html.escape(spec.get("source", "")))
    )

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(out)
        tmp = tf.name

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        pg.goto("file://" + tmp)
        pg.wait_for_timeout(400)
        pg.screenshot(path=out_path)
        b.close()
    os.unlink(tmp)
    print(f"news card written: {out_path}")


if __name__ == "__main__":
    main()
