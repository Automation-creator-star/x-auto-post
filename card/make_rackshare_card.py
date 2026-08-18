#!/usr/bin/env python3
"""Render a RackShare card PNG from a JSON spec.

Usage: python3 make_rackshare_card.py spec.json output.png

Spec fields:
  badge     - top-right pill, e.g. "インフラエンジニアの知識共有"
  headline  - main line; <span class="y">..</span> gold, <span class="c">..</span> cyan.
  head_size - optional headline font px (default 54; 46-50 for long ones)
  points    - list of 2-3 short benefit strings (<b>..</b> highlight)
  cta_big   - CTA line, e.g. "無料ではじめる"
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
    with open(os.path.join(HERE, "rackshare_template.html"), encoding="utf-8") as f:
        tmpl = f.read()

    pts = "".join(
        f'<div class="pt"><span class="ck">✓</span><span>{p}</span></div>'
        for p in (spec.get("points") or [])
    )
    out = (
        tmpl.replace("__HEAD_SIZE__", str(spec.get("head_size", 54)))
        .replace("__BADGE__", _html.escape(spec.get("badge", "インフラエンジニアの知識共有")))
        .replace("__HEADLINE__", spec["headline"])
        .replace("__POINTS__", pts)
        .replace("__CTA_BIG__", _html.escape(spec.get("cta_big", "無料ではじめる")))
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
    print(f"rackshare card written: {out_path}")


if __name__ == "__main__":
    main()
