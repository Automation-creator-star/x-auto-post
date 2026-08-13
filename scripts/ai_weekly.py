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

# NESPE campaign: during this window the night slot becomes a campaign post
# driving to the LP (replacing the usual career / LINE-CCNA nights).
CAMPAIGN_END = datetime.date(2026, 8, 27)
LP_URL = "https://lp.theit.co.jp/p/8bJgbvOT0crt?ftid=fnnF6ycboBC4"


def wlen(text):
    """X weighted length: JP/full-width = 2, ASCII = 1, each URL counts as 23."""
    t = re.sub(r"https?://\S+", "x" * 23, text)
    n = 0
    for ch in t:
        n += 1 if ord(ch) < 0x100 else 2
    return n


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
    # strict=False tolerates raw newlines/tabs the model sometimes emits
    # inside JSON string values (e.g. the multi-line "post" field).
    return json.loads(m.group(1), strict=False)


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


CAMPAIGN_ANGLES = [
    "IPAの制度改正で現行制度は2026年度で終了予定。『ネットワークスペシャリスト』という独立区分で受けられるのは今年が最後、という緊急性",
    "独学で一番の遠回りは『何から・どの順で』の迷い。まず学習ロードマップで解消できる、という切り口",
    "働きながらでも、実務経験が浅くても、正しい順番と教材があれば最短で狙える、という背中押し",
    "本番の必修講義(R7年度版・必修講義版)を14日間そのまま無料で体験できる、というオファーの中身",
    "積み上げたネットワークの知識を『国家資格』で証明すると、仕事や転職で活きる、という価値",
    "2026年度の試験スケジュール(申込10/6〜、科目A 10/17〜、科目B 11/11〜)を示し、今からでも約2ヶ月ある、という現実的な後押し",
    "『いつかネスペを』で止まっている人へ。まず14日間無料で、続けるかは後で決めればいい、というハードル下げ",
]


def gen_campaign(api_key, angle, extra=""):
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表)の夜の投稿を作ります。無料キャンペーンの告知を1つ。
オファー: 国家資格「ネットワークスペシャリスト(ネスペ)」の合格講座eラーニング(R7年度版・必修講義版)を14日間無料開放+学習ロードマップ。提供は株式会社iT。現行のネスペ試験制度は2026年度で終了予定で、独立区分で受けられるのは今年が最後。誇大表現(絶対合格・誰でも等)は禁止。事実に基づき誠実に。
今回の切り口: {angle}

【本文の絶対条件】とても短くまとめる。構成は「①切り口の要点1文（40字以内）→ ②14日間無料を一言で（30字以内）→ 改行して {LP_URL} → ④短い一言CTA（例: 本文のリンクから今すぐ）」。CTAは必ず「本文のリンクから」等と言い、「プロフ(ィール)のリンクから」とは絶対に書かない(URLは本文内にあるため)。長い説明・複数段落は禁止。日本語全角=2/半角=1・URL=23として、全体で必ず250単位以内に収める(超えたら短くやり直す)。ハッシュタグは付けても #ネスペ を1個だけ、無くてもよい。{extra}

次のJSONだけを```json ... ```で出力:
{{
 "post": "上記条件を厳守した短い投稿本文。改行で {LP_URL} を必ず1回含める。",
 "badge": "カード上部の短いバッジ。例: 期間限定・14日間無料",
 "last": "見出し上の小さな一言。例: ＼ “ネスペ”として挑めるのは今年が最後 ／",
 "headline": "カードの主見出し。<span class=\\"y\\">語句</span>でゴールド強調可。全角24字程度。",
 "head_size": 54,  // 長い場合は 48
 "points": ["特典・魅力を短く2〜3個。<b>語句</b>で強調可。例: ネスペ講座を14日間 無料"],
 "cta_big": "本文のリンクから今すぐ無料で"
}}"""
    s = anthropic(api_key, prompt, max_tokens=1500)
    # Length guard: X limit is 280 weighted; regenerate shorter if needed.
    for _ in range(2):
        if wlen(s.get("post", "")) <= 270:
            break
        s = anthropic(
            api_key,
            prompt + f"\n\n【再指示】前回の本文が長すぎました。{LP_URL} を除いた地の文を大幅に削り、全体を230単位以内に必ず収めてください。",
            max_tokens=1500,
        )
    return s


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
        npng = os.path.join(ROOT, "queue", f"{date}-night.png")
        campaign = d <= CAMPAIGN_END

        # During the campaign window the night slot is a NESPE campaign post.
        # If an existing (non-campaign) night is queued, replace it. If tonight
        # is already posted, leave it. Outside the window, only fill gaps.
        already_campaign = os.path.exists(ntxt) and LP_URL[:22] in open(ntxt, encoding="utf-8").read()
        do_night = (
            not os.path.exists(nposted)
            and (
                (campaign and not already_campaign)
                or (not campaign and not os.path.exists(ntxt))
            )
        )
        if do_night:
            try:
                if campaign:
                    angle = CAMPAIGN_ANGLES[i % len(CAMPAIGN_ANGLES)]
                    s = gen_campaign(api_key, angle)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    render("make_campaign_card.py",
                           {k: s[k] for k in ("badge", "last", "headline", "points", "cta_big") if k in s}
                           | ({"head_size": s["head_size"]} if s.get("head_size") else {}),
                           npng)
                    made.append(f"{date} night: campaign")
                elif wd in (1, 4):  # Tue / Fri -> link post + LINE banner
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
