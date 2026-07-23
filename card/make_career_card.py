#!/usr/bin/env python3
"""Render a キャリア (career advice) card PNG from a JSON spec.

Usage: python3 make_career_card.py spec.json output.png

Spec fields:
  badge     - short category label, e.g. "キャリア" / "学習法" / "転職"
  headline  - the core pull-quote message (keep punchy, ~2-3 lines).
              Wrap <span class="hi">..</span> to highlight a phrase in green.
  body      - 1-2 sentence supporting detail (optional).
  head_size - optional headline font px (default 50; use 42-46 for long ones)

Requires playwright + chromium and Noto Sans CJK JP fonts.
"""
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

    with open(os.path.join(HERE, "career_template.html"), encoding="utf-8") as f:
        tmpl = f.read()

    out = (
        tmpl.replace("__HEAD_SIZE__", str(spec.get("head_size", 50)))
        .replace("__BADGE__", spec.get("badge", "キャリア"))
        .replace("__HEADLINE__", spec["headline"])
        .replace("__BODY__", spec.get("body", ""))
    )

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(out)
        tmp = tf.name

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=2)
        pg.goto("file://" + tmp)
        pg.wait_for_timeout(400)
        pg.screenshot(path=out_path)
        b.close()
    os.unlink(tmp)
    print(f"career card written: {out_path}")


if __name__ == "__main__":
    main()
