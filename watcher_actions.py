#!/usr/bin/env python3
"""
Seat watcher — phone/cloud edition.
Works TWO ways with the exact same file:
  1. GitHub Actions (recommended): runs in the cloud every 5 min, sends the
     alert to your phone via Telegram. Phone does nothing but receive it.
     Credentials come from Actions Secrets (env vars) — don't hardcode them
     if your repo is public.
  2. Termux on Android: python watcher_actions.py   (loop mode, default)
     Edit the PASTE_* values below, or export env vars.

Usage:  python watcher_actions.py --once     # single check (Actions mode)
        python watcher_actions.py            # watch forever (Termux mode)
"""

import json, os, smtplib, subprocess, sys, time, urllib.request
from email.mime.text import MIMEText

API = "https://www.conuplanner.com/api/check-seats"
TERM, SUBJECT, NUMBER = "2262", "ENGR", "251"   # 2262 = Fall 2026
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
INTERVAL = int(os.environ.get("INTERVAL", "60"))   # seconds (loop mode)

# --- Telegram: env var first (Actions Secrets), fallback to hardcoded ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "PASTE_TOKEN_HERE"
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT") or "PASTE_CHAT_ID"


def check():
    body = json.dumps({"term": TERM, "subject": SUBJECT, "number": NUMBER}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())["data"]


def telegram(text):
    if "PASTE_" in TELEGRAM_TOKEN or "PASTE_" in TELEGRAM_CHAT:
        print("(telegram not configured — skipping)")
        return
    body = json.dumps({"chat_id": int(TELEGRAM_CHAT), "text": text}).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN,
        data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15).read()
    print("telegram alert sent!")


def buzz(text):
    """Tiny buzz in Termux so the phone itself vibrates (needs termux-api)."""
    try:
        subprocess.Popen(["termux-vibrate", "-d", "1500"])
    except Exception:
        pass
    print("\a" * 3)
    print(text)


def alert(sections):
    lines = "\n".join("  %s  %s  ->  %s" % (s["classNbr"], s["section"], s["status"].upper())
                      for s in sections)
    text = ("*** ENGR 251 SEAT OPEN! ***\n%s\n\nEnroll NOW:\nMyConcordia -> Student Center\n"
            "https://myconcordia.ca" % lines)
    buzz(text)
    telegram(text)


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def run_once():
    state, sections = load_state(), check()
    hits = [s for s in sections
            if "open" in s["status"].lower() or "wait" in s["status"].lower()]
    if state:  # empty state = first ever run -> just record baseline
        changed = [s for s in sections if state.get(s["classNbr"]) != s["status"]]
        for s in changed:
            print("changed:", s["classNbr"], s["section"],
                  state.get(s["classNbr"]), "->", s["status"])
        if hits:
            alert(hits)
        else:
            print("no open seats (%d sections checked)." % len(sections))
    else:
        print("baseline saved:")
        for s in sections:
            print("  %s %s = %s" % (s["classNbr"], s["section"], s["status"]))
    json.dump({s["classNbr"]: s["status"] for s in sections}, open(STATE_FILE, "w"))
    return hits


if __name__ == "__main__":
    if "--test-telegram" in sys.argv:
        print("sending a Telegram test message...")
        telegram("🧪 Test alert — your seat watcher's Telegram wiring works!\n\n"
                 "When ENGR 251 opens, this is how you'll get pinged.")
    elif "--once" in sys.argv:
        run_once()
    else:
        print("watching ENGR %s term %s every %ss — Ctrl+C stops" % (NUMBER, TERM, INTERVAL))
        errors = 0
        while True:
            try:
                run_once(); errors = 0; time.sleep(INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                errors += 1
                wait = min(600, INTERVAL * errors * 2)
                print("error:", e, "- retry in", wait, "s"); time.sleep(wait)
