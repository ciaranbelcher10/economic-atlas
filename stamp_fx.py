"""
Stamp each exchange-rate block (fx_to_usd, fx_to_eur, fx_eur_usd) with
confirmed_at when this run fetched it from its source.

Why this exists
---------------
series_guard.apply_guard() stamps every entry in out["series"] with
confirmed_at, which is what the freshness lights read ("matches the latest
release, checked 2 hours ago" versus "couldn't refresh for 5 days"). The FX
blocks sit outside out["series"], so they were never stamped, and since
v1.6.12 every Markets exchange-rate tile fell back to the old age-only rule:
a rate carried over from a failed fetch still showed green.

How it tells fresh from carried over, without touching 31 fetch scripts
------------------------------------------------------------------------
Every fetch script builds the block as a brand-new dict when the source
answers, so a fresh block has no confirmed_at. When the fetch fails, the
script copies the previous run's block verbatim, and that copy still carries
the stamp from the run that last fetched it. So:

    no confirmed_at   fetched this run  -> stamp now
    confirmed_at      carried over      -> leave it alone, it keeps ageing

Run after all fetch scripts and before "Commit updated data". Idempotent
within a run: a second call finds every block already stamped.
"""
import json
import os
from datetime import datetime, timezone

from check_data_freshness import DATA_FILES

FX_KEYS = ("fx_to_usd", "fx_to_eur", "fx_eur_usd")


def stamp(base_dir="."):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    stamped = []
    for country, filename in DATA_FILES.items():
        path = os.path.join(base_dir, filename)
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        indent = 2 if _indented(path, base_dir) else None
        changed = False
        for key in FX_KEYS:
            block = payload.get(key)
            if isinstance(block, dict) and block.get("history") and not block.get("confirmed_at"):
                block["confirmed_at"] = now
                stamped.append(f"{country}:{key}")
                changed = True
        if changed:
            with open(path, "w") as f:
                json.dump(payload, f, indent=indent)
    print(f"stamp_fx: {len(stamped)} exchange-rate block(s) confirmed this run"
          + (": " + ", ".join(stamped) if stamped else ""))
    return stamped


def _indented(path, base_dir):
    # Keep each file's existing layout so the committed diff stays readable.
    try:
        with open(path) as f:
            head = f.read(40)
        return "\n" in head
    except OSError:
        return False


if __name__ == "__main__":
    stamp()
