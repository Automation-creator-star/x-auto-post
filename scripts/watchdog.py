#!/usr/bin/env python3
"""Safety net: make sure each slot actually got posted, self-heal if not.

Runs near the END of each posting window (triggered reliably). For today's
current slot it checks whether posted/<date>-<slot>.txt exists. If it does,
the normal flow worked -> stay silent. If it does NOT, the normal flow missed:
  1. if the queued content is missing, generate it (news for noon, ai_weekly
     for morning/night),
  2. then post it (FORCE_SLOT),
  3. then notify Chatwork of what happened (auto-recovered, or still-failed).

So even if generation OR posting triggers ever fail, this catches it within the
window, fixes it, and alerts -- nothing is missed silently.

Env: X creds (CONSUMER_KEY/SECRET, ACCESS_TOKEN/SECRET), ANTHROPIC_API_KEY,
CHATWORK_API_TOKEN, CHATWORK_ROOM_ID, optional FORCE_SLOT.
"""
import datetime
import os
import subprocess
import sys
import urllib.parse
import urllib.request

JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOT_JP = {"morning": "朝(用語解説)", "noon": "昼(ITニュース)",
           "evening": "夕方(RackShare)", "night": "夜"}


def current_slot(now):
    h = now.hour
    if 8 <= h <= 11:
        return "morning"
    if 12 <= h <= 17:
        return "noon"
    if 18 <= h <= 20:
        return "evening"
    if 21 <= h <= 23:
        return "night"
    return None


def notify(message):
    token = os.environ.get("CHATWORK_API_TOKEN")
    room = os.environ.get("CHATWORK_ROOM_ID")
    if not token or not room:
        print("[watchdog] no Chatwork creds; skipping notify")
        return
    try:
        req = urllib.request.Request(
            f"https://api.chatwork.com/v2/rooms/{room}/messages",
            data=urllib.parse.urlencode({"body": message, "self_unread": 1}).encode(),
            headers={"X-ChatWorkToken": token},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
        print("[watchdog] Chatwork notified")
    except Exception as e:  # noqa: BLE001
        print(f"[watchdog] Chatwork notify failed: {e}", file=sys.stderr)


def run(script, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", script)],
                       env=env, capture_output=True, text=True)
    print(f"[watchdog] {script} rc={r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.returncode == 0


def main():
    now = datetime.datetime.now(JST)
    slot = os.environ.get("FORCE_SLOT") or current_slot(now)
    if not slot:
        print(f"[watchdog] hour {now.hour} JST is outside any window; nothing to check.")
        return

    date = f"{now:%Y-%m-%d}"
    posted = os.path.join(ROOT, "posted", f"{date}-{slot}.txt")
    queue = os.path.join(ROOT, "queue", f"{date}-{slot}.txt")
    label = SLOT_JP.get(slot, slot)

    if os.path.exists(posted):
        print(f"[watchdog] {date} {slot} already posted; all good.")
        return

    print(f"[watchdog] {date} {slot} NOT posted -> attempting self-heal")

    # 1) generate content if missing
    if not os.path.exists(queue):
        gen = "ai_news.py" if slot == "noon" else "ai_weekly.py"
        print(f"[watchdog] queue missing -> generating via {gen}")
        run(gen)

    if not os.path.exists(queue):
        notify(
            f"[toaster] 🚨 自動投稿ウォッチドッグ\n{date} の{label}が投稿できていません。"
            f"本文の自動生成にも失敗したため、投稿を見送りました。手動での確認をお願いします。"
        )
        return

    # 2) post it (force this slot regardless of exact minute)
    run("post.py", {"FORCE_SLOT": slot})

    # 3) verify + alert
    if os.path.exists(posted):
        notify(
            f"[toaster] ⚠️ 自動投稿ウォッチドッグ\n{date} の{label}が通常フローで出ていませんでした。"
            f"ウォッチドッグが自動で生成・投稿まで復旧しました（投稿は完了済み）。"
        )
    else:
        notify(
            f"[toaster] 🚨 自動投稿ウォッチドッグ\n{date} の{label}の投稿に失敗しました"
            f"（本文はあるが投稿処理でエラー）。X側の認証や文字数など、手動確認をお願いします。"
        )


if __name__ == "__main__":
    main()
