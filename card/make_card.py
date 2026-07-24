#!/usr/bin/env python3
"""Render a 用語解説 card PNG from a JSON spec.

Usage: python3 make_card.py spec.json output.png

Spec fields:
  term        - the term, e.g. "VLAN" (displayed huge)
  sub         - subtitle, e.g. "Virtual LAN／仮想LAN"
  desc        - HTML fragment; use <b>..</b> for cyan highlights
  diagram     - inline SVG (width<=1072, height<=210) illustrating the term
  term_size   - optional font px for the term (default 110; use smaller
                for long/Japanese terms, e.g. 72)

Requires playwright + chromium (PLAYWRIGHT_BROWSERS_PATH preconfigured)
and Noto Sans CJK JP fonts.
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

    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        html = f.read()

    html = (
        html.replace("__TERM_SIZE__", str(spec.get("term_size", 110)))
        .replace("__TERM__", spec["term"])
        .replace("__SUB__", spec.get("sub", ""))
        .replace("__DESC__", spec["desc"])
        .replace("__DIAGRAM__", spec.get("diagram", ""))
    )

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp = tf.name

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        pg.goto("file://" + tmp)
        pg.wait_for_timeout(400)
        pg.screenshot(path=out_path)
        b.close()
    os.unlink(tmp)
    print(f"card written: {out_path}")


if __name__ == "__main__":
    main()
