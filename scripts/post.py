#!/usr/bin/env python3
"""Queue-based X posting script, run by GitHub Actions on a schedule.

Determines the current slot from JST time, looks for
queue/YYYY-MM-DD-<slot>.txt, posts its contents to X, then moves the
file to posted/. Missing queue file = skip quietly (exit 0).

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

    fname = f"{now:%Y-%m-%d}-{slot}.txt"
    path = os.path.join(ROOT, "queue", fname)
    if not os.path.exists(path):
        print(f"No queued post at queue/{fname}; skipping.")
        return

    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print(f"queue/{fname} is empty; skipping.")
        return

    client = tweepy.Client(
        consumer_key=os.environ["CONSUMER_KEY"],
        consumer_secret=os.environ["CONSUMER_SECRET"],
        access_token=os.environ["ACCESS_TOKEN"],
        access_token_secret=os.environ["ACCESS_TOKEN_SECRET"],
    )
    try:
        resp = client.create_tweet(text=text)
    except tweepy.errors.Forbidden as e:
        # e.g. duplicate content; archive so we don't retry forever
        print(f"Forbidden (possibly duplicate): {e}", file=sys.stderr)
        shutil.move(path, os.path.join(ROOT, "posted", "FAILED-" + fname))
        sys.exit(1)

    tweet_id = resp.data["id"]
    print(f"Posted {fname}: https://x.com/nespe_shacho/status/{tweet_id}")
    shutil.move(path, os.path.join(ROOT, "posted", fname))


if __name__ == "__main__":
    main()
