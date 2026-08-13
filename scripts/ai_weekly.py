#!/usr/bin/env python3
"""Fill the next 7 days of morning (term) + night (career/link) content.

Runs in GitHub Actions. For each of the next 7 JST dates that has no content
yet, generates via the Anthropic API and renders the card image:
  morning: 【用語解説】term post  + blue diagram card
  night  : career message post    + green message card
           (Tuesdays & Fridays instead: LINE-course link post + fixed banner)

Only fills gaps (never overwrites an existing queue/posted file), so it is safe
to run daily as a self-healing backfill as well as weekly.

Env: ANTHROPIC_API_KEY (required).
"""
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import urllib.request

MODEL = "claude-sonnet-4-5"
JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE_URL = "https://x.gd/Et9Ri"
BANNER = os.path.join(ROOT, "assets", "line_banner.png")


def anthropic(api_key, prompt, max_tokens=1500):
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL) or re.search(r"(\{.*\})", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in output: " + text[:400])
    return json.loads(m.group(1))


def used_terms():
    terms = set()
    for d in ("queue", "posted"):
        for p in glob.glob(os.path.join(ROOT, d, "*-morning.txt")):
            try:
                first = open(p, encoding="utf-8").readline()
            except OSError:
                continue
            mm = re.search(r"【用語解説】(.+?)とは", first)
            if mm:
                terms.add(mm.group(1).strip())
    return terms


def render(script, spec, out_png):
    """Render a card; on failure (e.g. bad SVG) retry with diagram removed."""
    spec_path = out_png.replace(".png", ".spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "card", script), spec_path, out_png], check=True)
    except subprocess.CalledProcessError:
        spec.pop("diagram", None)
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        subprocess.run([sys.executable, os.path.join(ROOT, "card", script), spec_path, out_png], check=True)
    os.remove(spec_path)


def gen_morning(api_key, avoid):
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、CCNA/ネットワーク教育)の朝の投稿を作ります。CCNA/ネットワークの重要用語を1つ、初学者向けに解説してください。既出の用語は避ける。既出: {', '.join(sorted(avoid)) or 'なし'}

次のJSONだけを```json ... ```で出力:
{{
 "term": "英略語などの用語名(例: ARP)",
 "sub": "正式名称/和名(例: Address Resolution Protocol)",
 "term_size": 110,  // 用語が長い場合(日本語など)は72程度に
 "desc": "初学者向け解説。<b>語句</b>で水色強調可。全角60字程度。",
 "diagram": "その用語の仕組みが一目で分かる簡潔なSVG。viewBox=\\"0 0 1072 300\\"。濃紺背景に映える配色(白=#fff, 水色=#38bdf8/#7dd3fc, 緑=#4ade80, 黄=#fbbf24)。角丸rect+矢印+textで構成。文字はfont-size 24〜30, font-weight 700。日本語可。壊れたSVGは不可、必ず妥当なSVG。",
 "post": "【用語解説】<term>とは\\n<解説文2〜3文>\\n\\n#CCNA という形の投稿本文。日本語全角=2/半角=1で270単位以内。URLは入れない。末尾のハッシュタグは #CCNA だけ(他のタグは絶対に付けない)。"
}}"""
    return anthropic(api_key, prompt, max_tokens=2000)


def gen_career(api_key):
    prompt = """あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・元インフラエンジニア、CCNA教育)の夜の投稿を作ります。未経験からの転職・学習法・資格の価値・実務での成長などを、元インフラエンジニア社長の目線で前向きに1つ。

次のJSONだけを```json ... ```で出力:
{
 "badge": "キャリア",
 "headline": "投稿の核となる一言を引用調で。<span class=\\"hi\\">語句</span>で緑強調可。<br>で改行可。全角30字程度。",
 "head_size": 50,  // 長い場合は42〜46
 "body": "補足1〜2文。",
 "post": "夜の投稿本文。上記の核を含め具体的で前向きに。文末に空行を挟んで読者が返信したくなる短い問いかけを1文。日本語全角=2/半角=1で270単位以内。URLは入れない。"
}"""
    return anthropic(api_key, prompt, max_tokens=1500)


def gen_link(api_key, pattern):
    style = ("質問への回答+実績(資格取得者1,000名超・転職成功800名超)で自然に誘導"
             if pattern == "C" else
             "学習法・挫折ポイントの話から『学習手順を無料LINE講座にまとめた』と誘導。文末に『毎日5分読むだけの構成です。』等の一言")
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、CCNA教育)の夜の投稿を作ります。無料のLINE CCNA講座({LINE_URL})への誘導投稿を1つ。{style}。宣伝くさくなりすぎず自然に。#タグや問いかけは不要。

次のJSONだけを```json ... ```で出力:
{{"post": "投稿本文。改行で {LINE_URL} を必ず1回含める。日本語全角=2/半角=1・URLは23としてで270単位以内。"}}"""
    return anthropic(api_key, prompt, max_tokens=800)


def main():
    api_key = os.environ["ANTHROPIC_API_KEY"]
    today = datetime.datetime.now(JST).date()
    avoid = used_terms()
    made = []

    for i in range(7):
        d = today + datetime.timedelta(days=i)
        date = d.isoformat()
        wd = d.weekday()  # Mon=0 .. Sun=6

        # morning
        mtxt = os.path.join(ROOT, "queue", f"{date}-morning.txt")
        mposted = os.path.join(ROOT, "posted", f"{date}-morning.txt")
        if not os.path.exists(mtxt) and not os.path.exists(mposted):
            try:
                s = gen_morning(api_key, avoid)
                open(mtxt, "w", encoding="utf-8").write(s["post"].strip())
                render("make_card.py", {k: s[k] for k in ("term", "sub", "desc", "diagram") if k in s}
                       | ({"term_size": s["term_size"]} if s.get("term_size") else {}),
                       os.path.join(ROOT, "queue", f"{date}-morning.png"))
                avoid.add(s.get("term", "").strip())
                made.append(f"{date} morning: {s.get('term')}")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} morning failed: {e}", file=sys.stderr)

        # night
        ntxt = os.path.join(ROOT, "queue", f"{date}-night.txt")
        nposted = os.path.join(ROOT, "posted", f"{date}-night.txt")
        if not os.path.exists(ntxt) and not os.path.exists(nposted):
            try:
                npng = os.path.join(ROOT, "queue", f"{date}-night.png")
                if wd in (1, 4):  # Tue / Fri -> link post + LINE banner
                    pattern = "C" if wd == 1 else "A"
                    s = gen_link(api_key, pattern)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    subprocess.run(["cp", BANNER, npng], check=True)
                    made.append(f"{date} night: link({pattern})")
                else:
                    s = gen_career(api_key)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    render("make_career_card.py",
                           {k: s[k] for k in ("badge", "headline", "body") if k in s}
                           | ({"head_size": s["head_size"]} if s.get("head_size") else {}),
                           npng)
                    made.append(f"{date} night: career")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} night failed: {e}", file=sys.stderr)

    print("Generated:\n" + ("\n".join(made) if made else "(nothing — all 7 days already filled)"))


if __name__ == "__main__":
    main()
