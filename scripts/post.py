#!/usr/bin/env python3
"""Queue-based X posting script, run by GitHub Actions on a schedule.

Determines the current slot from JST time, looks for
queue/YYYY-MM-DD-<slot>.txt, posts its contents to X, then moves the
file to posted/. If a matching .png exists alongside the .txt, it is
uploaded and attached to the post (falls back to text-only if the
media upload fails). Missing queue file = skip quietly (exit 0).

Slots (JST): morning 08-11 / noon 12-14 / afternoon 15-17 / evening 18-20 / night 21-23
The workflow fires every ~20 minutes inside these windows; the first
run that finds the slot's queue file posts it (the file is then moved
to posted/, so later runs in the same window do nothing).
"""
import datetime
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request

import tweepy

JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def current_slot(now):
    h = now.hour
    # Windows are wide so a trigger (poke/cron) delayed by up to ~1-3h still
    # lands in the right slot. Each slot's queue file is posted once, then moved.
    if 8 <= h <= 11:
        return "morning"
    if 12 <= h <= 14:
        return "noon"
    if 15 <= h <= 17:
        return "afternoon"
    if 18 <= h <= 20:
        return "evening"
    if 21 <= h <= 23:
        return "night"
    return None


def notify_chatwork(message):
    """Send a message to Chatwork; never raise (notification is best-effort)."""
    token = os.environ.get("CHATWORK_API_TOKEN")
    room = os.environ.get("CHATWORK_ROOM_ID")
    if not token or not room:
        return
    try:
        req = urllib.request.Request(
            f"https://api.chatwork.com/v2/rooms/{room}/messages",
            # self_unread=1 marks the message unread even for the sender, so the
            # room shows an unread badge (Chatwork otherwise treats messages
            # posted with the owner's own token as already read).
            data=urllib.parse.urlencode({"body": message, "self_unread": 1}).encode(),
            headers={"X-ChatWorkToken": token},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
        print("Chatwork notified.")
    except Exception as e:  # noqa: BLE001
        print(f"Chatwork notification failed: {e}", file=sys.stderr)


def main():
    now = datetime.datetime.now(JST)
    slot = os.environ.get("FORCE_SLOT") or current_slot(now)
    if not slot:
        print(f"No slot for hour {now.hour} JST; nothing to do.")
        return

    base = f"{now:%Y-%m-%d}-{slot}"
    txt_path = os.path.join(ROOT, "queue", base + ".txt")
    png_path = os.path.join(ROOT, "queue", base + ".png")
    # Optional sidecars (2026-11-16):
    #   <base>.reply.txt  -> posted as a self-reply right after the main post
    #                        (used to put the link in the reply instead of the body)
    #   <base>.poll.json  -> {"options": [...], "duration_minutes": 1440} makes it a poll
    reply_path = os.path.join(ROOT, "queue", base + ".reply.txt")
    poll_path = os.path.join(ROOT, "queue", base + ".poll.json")
    if not os.path.exists(txt_path):
        print(f"No queued post at queue/{base}.txt; skipping.")
        return

    with open(txt_path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print(f"queue/{base}.txt is empty; skipping.")
        return

    auth_kwargs = dict(
        consumer_key=os.environ["CONSUMER_KEY"],
        consumer_secret=os.environ["CONSUMER_SECRET"],
        access_token=os.environ["ACCESS_TOKEN"],
        access_token_secret=os.environ["ACCESS_TOKEN_SECRET"],
    )
    client = tweepy.Client(**auth_kwargs)

    poll = None
    if os.path.exists(poll_path):
        try:
            with open(poll_path, encoding="utf-8") as f:
                pj = json.load(f)
            opts = [str(o)[:25] for o in pj.get("options", [])][:4]
            if len(opts) >= 2:
                poll = {"poll_options": opts,
                        "poll_duration_minutes": int(pj.get("duration_minutes", 1440))}
        except Exception as e:  # noqa: BLE001 - fall back to a normal post
            print(f"Poll spec unreadable, posting without poll: {e}", file=sys.stderr)

    media_ids = None
    if os.path.exists(png_path) and not poll:
        try:
            auth = tweepy.OAuth1UserHandler(
                auth_kwargs["consumer_key"],
                auth_kwargs["consumer_secret"],
                auth_kwargs["access_token"],
                auth_kwargs["access_token_secret"],
            )
            media = tweepy.API(auth).media_upload(png_path)
            media_ids = [media.media_id]
            print(f"Uploaded media {base}.png (id={media.media_id})")
        except Exception as e:  # noqa: BLE001 - fall back to text-only
            print(f"Media upload failed, posting text-only: {e}", file=sys.stderr)

    try:
        if poll:
            resp = client.create_tweet(text=text, **poll)
        elif media_ids:
            resp = client.create_tweet(text=text, media_ids=media_ids)
        else:
            resp = client.create_tweet(text=text)
    except Exception as e:
        # e.g. duplicate content; archive so we don't retry forever
        print(f"Post failed: {e}", file=sys.stderr)
        shutil.move(txt_path, os.path.join(ROOT, "posted", "FAILED-" + base + ".txt"))
        for ext in (".png", ".reply.txt", ".poll.json"):
            side = os.path.join(ROOT, "queue", base + ext)
            if os.path.exists(side):
                shutil.move(side, os.path.join(ROOT, "posted", "FAILED-" + base + ext))
        notify_chatwork(
            f"[info][title]X自動投稿: 失敗[/title]{base} の投稿に失敗しました。\n"
            f"エラー: {e}\n文面はリポジトリの posted/FAILED-{base}.txt に退避しています。[/info]"
        )
        sys.exit(1)

    tweet_id = resp.data["id"]
    url = f"https://x.com/nespe_shacho/status/{tweet_id}"
    print(f"Posted {base}: {url}")

    reply_note = ""
    if os.path.exists(reply_path):
        with open(reply_path, encoding="utf-8") as f:
            reply_text = f.read().strip()
        if reply_text:
            try:
                r2 = client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                print(f"Replied with link: https://x.com/nespe_shacho/status/{r2.data['id']}")
                reply_note = "\n(リンクは返信に投稿済み)"
            except Exception as e:  # noqa: BLE001 - main post is out; just report
                print(f"Reply failed: {e}", file=sys.stderr)
                reply_note = f"\n※リンクの返信に失敗: {e}"
    slot_names = {"morning": "朝・用語解説", "noon": "昼・ITニュース",
                  "afternoon": "15時・RackShare", "evening": "18時・年収診断", "night": "夜・キャリア"}
    notify_chatwork(
        f"[info][title]X自動投稿: 完了 ({slot_names.get(slot, slot)})[/title]"
        f"{text[:60]}{'…' if len(text) > 60 else ''}\n{url}{reply_note}[/info]"
    )
    shutil.move(txt_path, os.path.join(ROOT, "posted", base + ".txt"))
    for ext in (".png", ".reply.txt", ".poll.json"):
        side = os.path.join(ROOT, "queue", base + ext)
        if os.path.exists(side):
            shutil.move(side, os.path.join(ROOT, "posted", base + ext))


if __name__ == "__main__":
    main()
