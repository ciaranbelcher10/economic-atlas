#!/usr/bin/env python3
"""v1.9.64: the privacy page describes what the site actually collects.

The email signup list was removed (v1.9.31, table dropped 2 Nov 2026), so the
policy must not describe a signup list, newsletter unsubscribes or Resend
delivery for it. Email is collected only through account sign-up (Supabase
auth). Resend is named only for the opt-in calendar alerts, and only while
send_calendar_alerts.py still exists.
Run: python3 tools/test_privacy_page.py
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails, oks = [], 0
def check(cond, msg):
    global oks
    if cond: oks += 1
    else: fails.append(msg)

h = open(os.path.join(ROOT, "privacy.html"), encoding="utf-8").read()
m = re.search(r'<div class="roadmap">(.*?)</div>\s*<footer', h, re.S)
check(m, "policy body found")
body = m.group(1) if m else ""
text = re.sub(r"<[^>]+>", " ", body)
paras = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p)).strip()
         for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]

for bad in ["Email signup", "signup box", "sign up for email updates",
            "unsubscribe", "email list", "this list"]:
    check(bad.lower() not in text.lower(), "no stale phrase: " + bad)
heads = re.findall(r"<strong>([^<]+)</strong>", body)
check("Accounts" in heads, "Accounts section present")
check(any("Supabase" in p and "account" in p.lower() for p in paras), "Supabase named for accounts")
check(re.search(r"only collects your email address if you create an account", text), "short version says email only via account")

alerts = os.path.exists(os.path.join(ROOT, "send_calendar_alerts.py"))
check(("Calendar email alerts" in heads) == alerts, "calendar alerts section matches whether the feature exists")
for p in paras:
    if "Resend" in p:
        check(alerts and "calendar" in p.lower(), "Resend only named for calendar alerts: " + p[:60])
check(text.count("Resend") >= (2 if alerts else 0), "Resend named in alerts and access sections")
check(not re.search(r"until you unsubscribe", text), "retention not tied to unsubscribing")

print(f"{oks} ok, {len(fails)} failed")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
