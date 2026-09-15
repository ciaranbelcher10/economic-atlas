#!/usr/bin/env python3
"""
Workstream 2 harness: pull every testable claim out of the methodology and
FAQ pages so each can be checked against what the code actually does.

Extracts visible text only (drops script, style, and HTML comments), splits
into sentences, and flags the ones most likely to have quietly acquired an
exception: universals ("every", "all", "always", "never", "throughout"),
frequency promises ("hourly", "daily", "real time"), coverage counts
("32 countries", "128 pages"), and provenance claims ("official", "source").

Usage:
  python3 promise_extract.py <file.html> [more.html ...]
"""
import re, sys, html

UNIVERSAL = re.compile(
    r"\b(every|all|always|never|any|none|throughout|entirely|only|no )\b", re.I)
CADENCE = re.compile(
    r"\b(hourly|every hour|daily|每|real[- ]time|live|continuous|updated|refresh\w*)\b", re.I)
COUNTS = re.compile(r"\b\d{1,4}\b")
PROVENANCE = re.compile(
    r"\b(official|source[sd]?|publish\w*|statistic\w*|agency|agencies|"
    r"provider|institute|bureau|office)\b", re.I)
FORECAST = re.compile(
    r"\b(forecast\w*|projection\w*|estimate\w*|predict\w*|commentary|opinion)\b", re.I)


def visible_text(raw):
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    # block boundaries become sentence boundaries so headings don't glue on
    raw = re.sub(r"</(p|div|li|h[1-6]|td|section|details|summary)>", " \n ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def sentences(text):
    out = []
    for block in text.split("\n"):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", block):
            s = s.strip()
            if len(s) >= 25 and re.search(r"[a-z]{4}", s):
                out.append(s)
    return out


def classify(s):
    tags = []
    if UNIVERSAL.search(s):
        tags.append("UNIVERSAL")
    if CADENCE.search(s):
        tags.append("CADENCE")
    if PROVENANCE.search(s):
        tags.append("PROVENANCE")
    if FORECAST.search(s):
        tags.append("FORECAST")
    nums = [n for n in COUNTS.findall(s) if len(n) <= 4]
    if nums:
        tags.append("COUNT:" + ",".join(nums[:4]))
    return tags


if __name__ == "__main__":
    total = 0
    for path in sys.argv[1:]:
        raw = open(path, encoding="utf-8", errors="ignore").read()
        sents = sentences(visible_text(raw))
        print(f"\n===== {path}: {len(sents)} candidate sentences")
        for i, s in enumerate(sents, 1):
            tags = classify(s)
            if not tags:
                continue
            total += 1
            print(f"[{i:3}] {'|'.join(tags)}")
            print(f"      {s}")
    print(f"\n{total} testable claims flagged", file=sys.stderr)
