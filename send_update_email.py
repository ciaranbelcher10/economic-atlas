"""One-off product update email to account holders ("What's new on The Economic Atlas").

Run by hand from send-update-email.yml (workflow_dispatch only, never on a schedule). Uses the same
Resend account, sending domain and Supabase service_role read as send_calendar_alerts.py.

Modes:
  preview  Builds the email and writes update-email-preview.html and .txt. Reads no users and sends nothing.
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
SUBJECT = "What's new on The Economic Atlas"
SITE = "https://theeconomicatlas.com"
SITE_FONT = "'Avenir Next','Avenir','Nunito Sans',system-ui,sans-serif"   # single quotes: double quotes would end the style attribute

INTRO = ("You have an account on The Economic Atlas, so here is a short note on what has changed since "
         "the first version. The site still does one thing: official statistics with the source named on "
         "every figure, and no commentary.")

# (heading, body, link path)
ITEMS = [
    ("62 economies", "Up from 18 at launch. Each has its own page with headline figures and charts on output, "
     "prices, labour, money and markets, trade and public finances.", "/"),
    ("1,109 indicator pages", "One page per economy and series, with a chart, the source series and an "
     "embeddable version.", "/indicators/"),
    ("14 rankings", "GDP, growth, inflation, unemployment, interest rates, bond yields, debt and more, "
     "across every economy with data.", "/rankings/"),
    ("Compare", "Any set of economies side by side on one measure, as bars, lines or a map.", "/compare"),
    ("Chartmaker", "Build a chart from any series on the site and export it as PNG, SVG or CSV.", "/chartmaker"),
    ("Dashboard and saved charts", "Pin figures from any country into one view, and save charts to "
     "your account to open later.", "/dashboard"),
    ("Release calendar", "Upcoming data releases, with an optional weekly email for the countries and "
     "measures you track.", "/calendar"),
    ("USD, inflation and per capita", "Country pages, Compare and Chartmaker can convert to US dollars, "
     "adjust for inflation and show figures per person.", "/compare"),
    ("Data status and methodology", "The latest period and next release for every series, and the exact "
     "source behind every indicator.", "/data-status"),
]

OUTRO = ("If something looks wrong or you would like a country or series added, reply to this email.")
OPT_OUT = ("You are receiving this because you have an account on The Economic Atlas. To stop update "
           "emails like this one, reply with \"unsubscribe\". Calendar alerts are set separately on the "
           "Calendar page.")


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_text() -> str:
    out = [INTRO, ""]
    for h, b, p in ITEMS:
        out += [h, b, SITE + p, ""]
    out += [OUTRO, "", SITE, "", "-", OPT_OUT]
    return "\n".join(out)


def build_html() -> str:
    rows = "".join(f"""
              <tr><td style="padding:14px 0;border-top:1px solid #E7E2D8;font-family:{SITE_FONT};">
                <a href="{SITE}{p}" style="font-size:15px;font-weight:bold;color:#AD1E1E;text-decoration:none;">{esc(h)}</a>
                <div style="font-size:14px;line-height:1.5;color:#1A1A1A;padding-top:3px;">{esc(b)}</div>
              </td></tr>""" for h, b, p in ITEMS)
    return f"""<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:#F4F1EA;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F4F1EA;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#FFFFFF;border:1px solid #E7E2D8;border-radius:6px;">
          <tr><td style="padding:28px 32px 20px 32px;border-bottom:2px solid #1A1A1A;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>
              <td style="padding-right:10px;"><img src="{SITE}/logo-64.png" width="28" height="28" alt="" style="display:block;border-radius:50%;"></td>
              <td style="font-family:{SITE_FONT};font-size:19px;color:#1A1A1A;font-weight:bold;">What's new on The Economic Atlas</td>
            </tr></table>
          </td></tr>
          <tr><td style="padding:20px 32px 6px 32px;font-family:{SITE_FONT};font-size:14px;line-height:1.5;color:#1A1A1A;">{esc(INTRO)}</td></tr>
          <tr><td style="padding:6px 32px 8px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}
            </table>
          </td></tr>
          <tr><td style="padding:8px 32px 0 32px;font-family:{SITE_FONT};font-size:14px;line-height:1.5;color:#1A1A1A;">{esc(OUTRO)}</td></tr>
          <tr><td align="center" style="padding:24px 32px 28px 32px;">
            <a href="{SITE}" style="display:inline-block;font-family:{SITE_FONT};font-size:15px;font-weight:bold;color:#FFFFFF;background-color:#1A1A1A;text-decoration:none;padding:12px 28px;border-radius:5px;">Open The Economic Atlas</a>
          </td></tr>
          <tr><td style="padding:16px 32px 24px 32px;border-top:1px solid #E7E2D8;font-family:{SITE_FONT};font-size:12px;line-height:1.5;color:#8A8375;">{esc(OPT_OUT)}</td></tr>
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
        open("update-email-preview.html", "w").write(html)
        open("update-email-preview.txt", "w").write(text)
        print("Wrote update-email-preview.html and update-email-preview.txt. Nothing sent.")
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
