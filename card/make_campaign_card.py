#!/usr/bin/env python3
"""Render a NESPE campaign card PNG from a JSON spec.

Usage: python3 make_campaign_card.py spec.json output.png

Spec fields:
  badge     - top pill text, e.g. "期間限定・14日間無料"
  last      - small line above headline, e.g. "＼ ネスペ本番、今年が最後 ／"
  headline  - main line; wrap <span class="y">..</span> for gold.
  head_size - optional headline font px (default 58; 48-52 for long ones)
  points    - list of short benefit strings (2-3), e.g. ["国家資格を14日間無料で体験", ...]
  cta_big   - big CTA line, e.g. "プロフィールのリンクから今すぐ"
  cta_sm    - small CTA line, e.g. "30秒で登録／いつでも配信停止OK"
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
    with open(os.path.join(HERE, "campaign_template.html"), encoding="utf-8") as f:
        tmpl = f.read()

    pts = "".join(
        f'<div class="pt"><span class="ck">✓</span><span>{p}</span></div>'
        for p in (spec.get("points") or [])
    )
    sm = (spec.get("cta_sm") or "").strip()
    sm_block = f'<div class="sm">{_html.escape(sm)}</div>' if sm else ""
    out = (
        tmpl.replace("__HEAD_SIZE__", str(spec.get("head_size", 58)))
        .replace("__BADGE__", _html.escape(spec.get("badge", "期間限定・無料")))
        .replace("__LAST__", _html.escape(spec.get("last", "")))
        .replace("__HEADLINE__", spec["headline"])
        .replace("__POINTS__", pts)
        .replace("__CTA_BIG__", _html.escape(spec.get("cta_big", "")))
        .replace("__CTA_SM_BLOCK__", sm_block)
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
    print(f"campaign card written: {out_path}")


if __name__ == "__main__":
    main()
