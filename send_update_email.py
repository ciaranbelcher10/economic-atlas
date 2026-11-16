"""One-off product update email to account holders ("What's new on The Economic Atlas").

Run by hand from send-update-email.yml (workflow_dispatch only, never on a schedule). Uses the same
Resend account, sending domain and Supabase service_role read as send_calendar_alerts.py.

Modes:
  preview  Builds the email and writes update-email-preview.html and .txt to the temp folder. Reads no users and sends nothing.
  test     Sends one copy to --to only. Reads no users.
  live     Sends to every account holder with an email except those who opted out, and only when
           --confirm SEND-TO-ALL is given. Otherwise it lists the recipient count and stops.

Opting out: a user who replies asking to stop gets preferences.product_updates_email = false in
profiles, and later runs skip them. Each live send carries a Resend Idempotency-Key built from
CAMPAIGN and the user id, so rerunning the same campaign within 24 hours cannot send twice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SUPABASE_URL = "https://skluvrxnuibkordzgtmu.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
FROM = "The Economic Atlas <alerts@theeconomicatlas.com>"
REPLY_TO = "alerts@theeconomicatlas.com"
CAMPAIGN = "update-v2-0"
SUBJECT = "The Economic Atlas now covers 62 economies"
# Inbox preview line, shown next to the subject and hidden in the email itself
PREHEADER = "Compare countries, build your own charts and see what is released this week."
SITE = "https://theeconomicatlas.com"
SITE_FONT = "'Avenir Next','Avenir','Nunito Sans',system-ui,sans-serif"   # single quotes: double quotes would end the style attribute

HEADLINE = "A lot has changed since you signed up"
INTRO = "The Economic Atlas has grown from 18 economies to 62. Every figure still comes from an official source, named on the page."

# (heading, one line, button label, link path)
ITEMS = [
    ("Compare any countries", "Put economies side by side on one measure, as bars, lines or a map.", "Open Compare", "/compare"),
    ("Make your own chart", "Pick any series on the site and download it as PNG, SVG or CSV.", "Open Chartmaker", "/chartmaker"),
    ("See what is released this week", "Upcoming data releases, with an optional weekly email for the ones you follow.", "Open the calendar", "/calendar"),
    ("Who ranks where", "14 rankings, from GDP and inflation to bond yields and debt.", "See the rankings", "/rankings/"),
]

ALSO = "Also new: your own Dashboard, saved charts, and switches to show figures in US dollars, after inflation or per person."
OUTRO = "Missing a country or a series? Reply and tell us."
OPT_OUT = ("You are receiving this because you have an account on The Economic Atlas. To stop update "
           "emails like this one, reply with \"unsubscribe\".")


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_text() -> str:
    out = [HEADLINE, "", INTRO, ""]
    for h, b, _, p in ITEMS:
        out += [h, b, SITE + p, ""]
    out += [ALSO, "", OUTRO, "", SITE, "", OPT_OUT]
    return "\n".join(out)


def build_html() -> str:
    f = SITE_FONT
    cards = "".join(f"""
          <tr><td style="padding:0 28px 12px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F7F5F0;border-radius:8px;">
              <tr><td style="padding:16px 18px;font-family:{f};">
                <div style="font-size:17px;font-weight:bold;color:#1A1A1A;">{esc(h)}</div>
                <div style="font-size:15px;line-height:1.45;color:#3A3A3A;padding:4px 0 10px 0;">{esc(b)}</div>
                <a href="{SITE}{p}" style="font-size:15px;font-weight:bold;color:#AD1E1E;text-decoration:none;">{esc(cta)} &rarr;</a>
              </td></tr>
            </table>
          </td></tr>""" for h, b, cta, p in ITEMS)
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light only">
    <title>{esc(SUBJECT)}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#F4F1EA;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{esc(PREHEADER)}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F4F1EA;">
      <tr><td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#FFFFFF;border-radius:10px;">
          <tr><td style="padding:24px 28px 0 28px;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>
              <td style="padding-right:10px;"><div style="background-color:#FFFFFF;border-radius:50%;width:32px;height:32px;"><img src="{SITE}/logo-64.png" width="32" height="32" alt="" style="display:block;border-radius:50%;"></div></td>
              <td style="font-family:{f};font-size:15px;font-weight:bold;color:#1A1A1A;">The Economic Atlas</td>
            </tr></table>
          </td></tr>
          <tr><td style="padding:22px 28px 6px 28px;font-family:{f};font-size:26px;line-height:1.2;font-weight:bold;color:#1A1A1A;">{esc(HEADLINE)}</td></tr>
          <tr><td style="padding:0 28px 20px 28px;font-family:{f};font-size:16px;line-height:1.5;color:#3A3A3A;">{esc(INTRO)}</td></tr>{cards}
          <tr><td style="padding:8px 28px 0 28px;font-family:{f};font-size:15px;line-height:1.5;color:#3A3A3A;">{esc(ALSO)}</td></tr>
          <tr><td align="center" style="padding:24px 28px 8px 28px;">
            <a href="{SITE}" style="display:block;font-family:{f};font-size:16px;font-weight:bold;color:#FFFFFF;background-color:#AD1E1E;text-decoration:none;padding:14px 20px;border-radius:6px;">Explore The Economic Atlas</a>
          </td></tr>
          <tr><td align="center" style="padding:8px 28px 24px 28px;font-family:{f};font-size:14px;color:#6B6B6B;">{esc(OUTRO)}</td></tr>
          <tr><td style="padding:16px 28px 22px 28px;border-top:1px solid #E7E2D8;font-family:{f};font-size:12px;line-height:1.5;color:#8A8375;">{esc(OPT_OUT)}</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def fetch_recipients() -> list[dict]:
    """Account holders who have not opted out. service_role read, as for calendar alerts."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        sys.exit("SUPABASE_SERVICE_ROLE_KEY not set: cannot read recipients.")
    url = f"{SUPABASE_URL}/rest/v1/profiles?select=id,email,preferences&email=not.is.null"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "User-Agent": "EconomicAtlas-UpdateEmail/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.loads(resp.read())
    out, seen = [], set()
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        if (r.get("preferences") or {}).get("product_updates_email") is False:
            continue
        seen.add(email)
        out.append({"id": r["id"], "email": email})
    return out


def send(to: str, text: str, html: str, idem: str | None) -> bool:
    if not RESEND_API_KEY:
        print("RESEND_API_KEY not set: nothing sent.", file=sys.stderr)
        return False
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json",
               "User-Agent": "EconomicAtlas-UpdateEmail/1.0"}
    if idem:
        headers["Idempotency-Key"] = idem
    body = json.dumps({"from": FROM, "to": [to], "reply_to": REPLY_TO, "subject": SUBJECT,
                       "text": text, "html": html}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"sent, Resend status {resp.status}")
            return True
    except urllib.error.HTTPError as exc:
        print(f"failed: HTTP {exc.code} {exc.read().decode('utf-8', 'replace')}", file=sys.stderr)
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preview", "test", "live"], default="preview")
    ap.add_argument("--to", help="test mode: the one address to send to")
    ap.add_argument("--confirm", default="", help="live mode: must be SEND-TO-ALL")
    a = ap.parse_args()
    text, html = build_text(), build_html()

    if a.mode == "preview":
        # written outside the repo: an .html file at the root fails generated_pages_gate.py
        import tempfile
        d = tempfile.gettempdir()
        open(os.path.join(d, "update-email-preview.html"), "w").write(html)
        open(os.path.join(d, "update-email-preview.txt"), "w").write(text)
        print(f"Wrote update-email-preview.html and .txt to {d}. Nothing sent.")
        return
    if a.mode == "test":
        if not a.to or "@" not in a.to:
            sys.exit("test mode needs --to with one email address.")
        print(f"Test send of '{SUBJECT}' to the given address: ", end="")
        sys.exit(0 if send(a.to.strip(), text, html, None) else 1)

    recipients = fetch_recipients()
    print(f"{len(recipients)} recipients (accounts with an email, opted-out removed).")
    if a.confirm != "SEND-TO-ALL":
        print("Not sending: live mode needs confirm = SEND-TO-ALL. This was a count only.")
        return
    sent = failed = 0
    for i, r in enumerate(recipients, 1):
        print(f"[{i}/{len(recipients)}] ", end="")   # addresses are never written to the log
        if send(r["email"], text, html, f"{CAMPAIGN}-{r['id']}"):
            sent += 1
        else:
            failed += 1
        time.sleep(0.6)   # Resend's default limit is 2 requests a second
    print(f"Done. Sent {sent}, failed {failed}.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
