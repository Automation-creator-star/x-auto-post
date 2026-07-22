#!/usr/bin/env python3
"""Queue-based X posting script, run by GitHub Actions on a schedule.

Determines the current slot from JST time, looks for
queue/YYYY-MM-DD-<slot>.txt, posts its contents to X, then moves the
file to posted/. If a matching .png exists alongside the .txt, it is
uploaded and attached to the post (falls back to text-only if the
media upload fails). Missing queue file = skip quietly (exit 0).

Slots (JST): morning 06-10 / noon 11-14 / night 19-23
"""
import datetime
import os
import shutil
import sys

import tweepy

JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def current_slot(now):
    h = now.hour
    if 6 <= h <= 10:
        return "morning"
    if 11 <= h <= 14:
        return "noon"
    if 19 <= h <= 23:
        return "night"
    return None


def main():
    now = datetime.datetime.now(JST)
    slot = os.environ.get("FORCE_SLOT") or current_slot(now)
    if not slot:
        print(f"No slot for hour {now.hour} JST; nothing to do.")
        return

    base = f"{now:%Y-%m-%d}-{slot}"
    txt_path = os.path.join(ROOT, "queue", base + ".txt")
    png_path = os.path.join(ROOT, "queue", base + ".png")
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

    media_ids = None
    if os.path.exists(png_path):
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
        if media_ids:
            resp = client.create_tweet(text=text, media_ids=media_ids)
        else:
            resp = client.create_tweet(text=text)
    except tweepy.errors.Forbidden as e:
        # e.g. duplicate content; archive so we don't retry forever
        print(f"Forbidden (possibly duplicate): {e}", file=sys.stderr)
        shutil.move(txt_path, os.path.join(ROOT, "posted", "FAILED-" + base + ".txt"))
        if os.path.exists(png_path):
            shutil.move(png_path, os.path.join(ROOT, "posted", "FAILED-" + base + ".png"))
        sys.exit(1)

    tweet_id = resp.data["id"]
    print(f"Posted {base}: https://x.com/nespe_shacho/status/{tweet_id}")
    shutil.move(txt_path, os.path.join(ROOT, "posted", base + ".txt"))
    if os.path.exists(png_path):
        shutil.move(png_path, os.path.join(ROOT, "posted", base + ".png"))


if __name__ == "__main__":
    main()
