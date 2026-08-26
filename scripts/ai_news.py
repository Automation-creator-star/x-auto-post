#!/usr/bin/env python3
"""Generate the daily noon ITニュース post + amber news card via the Anthropic API.

Runs inside GitHub Actions (which has open internet + a native GITHUB_TOKEN to
commit). Writes:
  queue/<JST-date>-noon.txt        the post text
  queue/<JST-date>-noon.png        the rendered news card
  card/specs/news-<JST-date>.json  the card spec (for reference / dedupe)

Skips (exit 0, writes nothing) if today's noon file already exists, or if no
solid, verifiable news is found.

Env: ANTHROPIC_API_KEY (required).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

MODEL = "claude-sonnet-4-5"
JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT = """あなたはX(Twitter)アカウント「ネスペ社長」(@nespe_shacho、株式会社iTの代表。CCNA/ネットワーク教育事業)の投稿を作るアシスタントです。今日の昼にXへ自動投稿する「ITニュース解説」を1件作ってください。伸びを最大化するため、Xで今注目されている話題(トレンド)を押さえた上でニュースを選びます。

手順:
1. web_search で、日本のXトレンド集計(getdaytrends.com/japan など)や「IT 障害 ニュース 今日」「セキュリティ 脆弱性」「クラウド 発表」などを調べ、直近24〜48時間のIT・ネットワーク・クラウド・セキュリティ・AI・大手IT・通信障害の話題を把握する。IT系がトレンド入り・大きく報じられていればそれを優先。
2. 事実確認できたニュースを1件選ぶ。必ず検索で裏取りできた事実だけを使い、推測や誇張は書かない。初学者〜若手インフラエンジニアの学びになり、かつ注目度が高いものを選ぶ。
3. 投稿文とカード用データを作る。

最終的に、余計な説明を一切付けず、次の形式のJSONだけを```json ... ```で出力すること:
{
  "found": true,
  "post_text": "【ITニュース】で始まる投稿本文。ニュースの要点1〜2文+初学者向けの補足や視点1〜2文。文末に(出典: 媒体名)。URLリンクは入れない。日本語全角=2・半角英数=1で数えた重み付き文字数で270以内。",
  "headline": "カードの見出し。全角22文字以内。強調したい語句は<span class=\\"hi\\">語句</span>で囲むとアンバー色になる。",
  "chips": ["数値やキーワードの短い文字列を最大3つ", "例: CVSS 9.9"],
  "body": "カード下部の初学者向け1〜2文の要約。",
  "source": "(出典: 媒体名)"
}
確実なニュースが無い・裏取りできない場合は {"found": false} だけを出力する(誤情報を出すより安全)。"""


def wlen(text):
    """X weighted length: JP/full-width=2, ASCII=1, each URL counts as 23."""
    t = re.sub(r"https?://\\S+", "x" * 23, text)
    return sum(1 if ord(c) < 0x100 else 2 for c in t)


def shorten(api_key, post):
    """Ask the model to shorten an over-long post, keeping facts + (出典:...)."""
    prompt = ("次のXポスト本文を、意味・事実・『(出典: …)』を保ったまま短くしてください。"
              "日本語全角=2/半角=1で数えて250以内。冒頭の【ITニュース】は残す。"
              "余計な説明やクォートは付けず、短くした本文だけを出力:\n\n" + post)
    body = {"model": MODEL, "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def call_anthropic(api_key):
    body = {
        "model": MODEL,
        "max_tokens": 2000,
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
        "messages": [{"role": "user", "content": PROMPT}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    # concatenate all text blocks
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return text


def extract_json(text):
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        m = re.search(r"(\{.*\})", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON found in model output:\n" + text[:500])
    return json.loads(m.group(1))


def main():
    api_key = os.environ["ANTHROPIC_API_KEY"]
    now = datetime.datetime.now(JST)
    date = f"{now:%Y-%m-%d}"
    txt_path = os.path.join(ROOT, "queue", f"{date}-noon.txt")
    posted_txt = os.path.join(ROOT, "posted", f"{date}-noon.txt")
    if os.path.exists(txt_path) or os.path.exists(posted_txt):
        print(f"{date}-noon already exists; nothing to do.")
        return

    text = call_anthropic(api_key)
    spec = extract_json(text)
    if not spec.get("found"):
        print("No solid news found; skipping today.")
        return

    post = spec["post_text"].strip()
    for _ in range(3):
        if wlen(post) <= 270:
            break
        try:
            post = shorten(api_key, post).strip()
        except Exception as e:  # noqa: BLE001
            print(f"[warn] shorten failed: {e}", file=sys.stderr)
            break
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(post)

    card_spec = {
        "headline": spec["headline"],
        "chips": spec.get("chips", []),
        "body": spec.get("body", ""),
        "source": spec.get("source", ""),
    }
    spec_path = os.path.join(ROOT, "card", "specs", f"news-{date}.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(card_spec, f, ensure_ascii=False, indent=2)

    png_path = os.path.join(ROOT, "queue", f"{date}-noon.png")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "card", "make_news_card.py"), spec_path, png_path],
        check=True,
    )
    print(f"Generated {date}-noon:\n{post}\n(card: {png_path})")


if __name__ == "__main__":
    main()
