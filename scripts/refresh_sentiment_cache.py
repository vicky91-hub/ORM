#!/usr/bin/env python3
"""
Freezes per-platform sentiment COUNTS (positive/negative/neutral tallies for the pie
charts) into theme_cache.json, keyed the same way the dashboard already keys narrative
themes: weekly (Monday-ISO date) and monthly (YYYY-MM).

This does NOT touch the existing qualitative "projects" narrative entries in
theme_cache.json (those are Claude-curated by reading real message text, not
mechanically derivable) — it only adds/refreshes a new top-level "sentimentCounts" key.

Only COMPLETE weeks/months get frozen. The current in-progress week and the current
in-progress month are deliberately left out of the cache — the dashboard falls back to
live computation from the currently-loaded sheet rows for those, since freezing a
month/week that hasn't finished yet would just go stale as more data arrives.

Run this every Monday (per the user's ask) to backfill the week that just completed:
    python3 scripts/refresh_sentiment_cache.py

Mirrors the exact aggregation logic in index.html's applyDateRange() — if that logic
changes, update this script to match (see the inline references to line-anchored
comments in index.html for what each block replicates).
"""
import csv
import io
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "theme_cache.json"

SHEET_IDS = {
    "redditQuora": "1pEp5zMru4ZqF339rb_glcbWe-XrAufiH5mUOgcQKPCs",
    "daily": "1IjbMN2n2n2xPNmLFifmM5yNYoxyPKi-TPTjdUa3Dbo0",
}

WEEK1_START = date(2026, 6, 22)  # Mon 22 Jun 2026 — must match WEEK1_START in index.html

GMB_PROJECTS = ['Folium', 'Edition', 'Capitol Residences', 'Panorama', 'Capitol Towers',
                'Elysium', 'Infracon', 'Z-hub', 'Hive and Thrive', 'Solace', 'Epitome']
GMB_PROJECT_ALIASES = {
    'capitol residency': 'Capitol Residences', 'capitol residences': 'Capitol Residences',
    'capitol towers': 'Capitol Towers', 'z-hub': 'Z-hub', 'zhub': 'Z-hub',
    'hive and thrive': 'Hive and Thrive', 'sumadhura hive': 'Hive and Thrive',
    'infracon': 'Infracon', 'sumadhura infracon private limited': 'Infracon',
    'folium': 'Folium', 'edition': 'Edition', 'panorama': 'Panorama',
    'elysium': 'Elysium', 'solace': 'Solace', 'epitome': 'Epitome',
}

MONTHS = {m.lower(): i for i, m in enumerate(
    ['January','February','March','April','May','June','July','August',
     'September','October','November','December'], start=1)}


# ---------- CSV / XLSX fetch (mirrors sheetCsvUrl / fetchSheetObjects / fetchWorkbookXlsx) ----------
def fetch_sheet_objects(sheet_id, tab):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={quote(tab, safe='')}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.text
    if text.strip().lower().startswith("<!doctype html"):
        raise RuntimeError(f"Got an HTML page instead of CSV for tab '{tab}' — sharing may have changed.")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    return [dict(zip(headers, [c.strip() for c in r])) for r in rows[1:]]


def fetch_sheet_objects_auto_header(sheet_id, tab, header_hint):
    """Same as fetch_sheet_objects, but locates the header row by content instead of
    assuming row 0 — mirrors fetchSheetObjectsAutoHeader() in index.html, for tabs with a
    stray formula/count row sitting above the real header in the live sheet."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={quote(tab, safe='')}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    rows = [r for r in csv.reader(io.StringIO(resp.text)) if any(c.strip() for c in r)]
    if not rows:
        return []
    header_row = next((i for i, r in enumerate(rows) if header_hint in [c.strip() for c in r]), 0)
    headers = [h.strip() for h in rows[header_row]]
    return [dict(zip(headers, [c.strip() for c in r])) for r in rows[header_row + 1:]]


def sanitize_url(raw):
    v = (raw or '').strip()
    if not v or ' ' in v or '.' not in v:
        return None
    if re.match(r'^https?://', v, re.I):
        return v
    if re.match(r'^www\.', v, re.I) or re.match(r'^[a-z0-9-]+\.[a-z]{2,}', v, re.I):
        return 'https://' + v
    return None


def has_comment_link(row):
    return sanitize_url(get_matching_row_value(row, ['Comment Link'])) is not None


_xlsx_cache = {}
def fetch_workbook_xlsx(sheet_id):
    if sheet_id in _xlsx_cache:
        return _xlsx_cache[sheet_id]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
    _xlsx_cache[sheet_id] = wb
    return wb


def fetch_sheet_objects_xlsx(sheet_id, tab):
    wb = fetch_workbook_xlsx(sheet_id)
    ws = wb[tab]
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else '' for h in next(rows_iter)]
    out = []
    for row in rows_iter:
        obj = {}
        for h, v in zip(header, row):
            if not h:
                continue
            obj[h] = v.strip() if isinstance(v, str) else v
        out.append(obj)
    return out


# ---------- Helpers (mirror numOr / getMatchingRowValue / normalizeHeaderName) ----------
def num_or(v, fallback):
    try:
        if v is None or v == '':
            return fallback
        return float(v)
    except (ValueError, TypeError):
        return fallback


def normalize_header_name(v):
    return (v or '').strip().lower()


def get_matching_row_value(row, candidates, exclude_fragments=()):
    for key in row.keys():
        key_name = normalize_header_name(key)
        if any(frag in key_name for frag in exclude_fragments):
            continue
        for candidate in candidates:
            cand = normalize_header_name(candidate)
            if key_name == cand or cand in key_name or key_name in cand:
                value = row[key]
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if value not in (None, ''):
                    return str(value).strip()
    return ''


def normalize_gmb_project(raw):
    if not raw:
        return None
    key = raw.strip().lower()
    if key in GMB_PROJECT_ALIASES:
        return GMB_PROJECT_ALIASES[key]
    for p in GMB_PROJECTS:
        if p.lower() in key:
            return p
    return None


def gmb_sentiment_from_recommendation(value):
    n = num_or(value, None)
    if n is None:
        return None
    if n >= 4:
        return 'positive'
    if n == 3:
        return 'neutral'
    return 'negative'


def platform_of(source):
    s = (source or '').lower()
    if 'instagram' in s:
        return 'Instagram'
    if 'facebook' in s:
        return 'Facebook'
    if 'linkedin' in s:
        return 'LinkedIn'
    if 'google business' in s:
        return 'GMB'
    return None


# ---------- Date parsing (mirrors parseDateValue) ----------
def parse_date_value(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r'^(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$', s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{2,4})', s)
    if m:
        day, mon_name, yr = int(m[1]), m[2].lower(), m[3]
        mon = next((v for k, v in MONTHS.items() if k.startswith(mon_name[:3])), None)
        if mon:
            year = 2000 + int(yr) if len(yr) == 2 else int(yr)
            return date(year, mon, day)
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3,})$', s)
    if m:
        day, mon_name = int(m[1]), m[2].lower()
        mon = next((v for k, v in MONTHS.items() if k.startswith(mon_name[:3])), None)
        if mon:
            return date(WEEK1_START.year, mon, day)
    return None


def get_row_date(row):
    for key in ['Post Publish date', 'Post Date', 'Comment Date', 'Date', 'Post date']:
        if key in row:
            parsed = parse_date_value(row[key])
            if parsed:
                return parsed
    return None


def monday_of(d):
    return d - timedelta(days=d.weekday())


# ---------- Data loaders ----------
def load_reddit_rows():
    """Mirrors loadRedditQuora()'s redditRows = [...threadRows, ...existingThreadRows].
    'Reddit - New Seeds' can have a stray formula/count row ahead of the real header, so its
    header is located by content ('Title / Question'), not assumed to be row 0. A row (in
    either tab) counts only if 'Comment Link' (the column right after 'Comment Status')
    holds a real URL — New Seeds has no per-row Total Upvotes/Comments columns at all, so
    the old Title+Upvotes check could never match a New Seeds row regardless of header
    detection."""
    seed_rows = fetch_sheet_objects_auto_header(SHEET_IDS["redditQuora"], "Reddit - New Seeds", "Title / Question")
    existing_rows = fetch_sheet_objects(SHEET_IDS["redditQuora"], "Reddit - Existing Threads")
    thread_rows = [r for r in seed_rows if has_comment_link(r)]
    existing_thread_rows = [r for r in existing_rows if has_comment_link(r)]
    return thread_rows + existing_thread_rows


def load_quora_sentiment():
    """Quora rows have no populated Post Date column in the source sheet — sentiment here
    is genuinely ungated by date in the live app (see applyDateRange()'s comment), so the
    same total is correct for every week/month bucket."""
    rows = fetch_sheet_objects(SHEET_IDS["redditQuora"], "Quora - New + Existing")
    thread_rows = [r for r in rows if r.get('Title / Question')]
    q_pos = sum(num_or(r.get('Positive comments'), 0) for r in thread_rows)
    q_neg = sum(num_or(r.get('Nagative Comments'), 0) for r in thread_rows)
    q_total = sum(num_or(r.get('Total Comments'), 0) for r in thread_rows)
    return {"positive": q_pos, "negative": q_neg, "neutral": max(0, q_total - q_pos - q_neg)}


def load_social_rows():
    """Mirrors loadDailyTracker(): raw tab, GMB sentiment from star rating, others from
    Final Sentiment. Uses the XLSX export (not CSV) because the raw tab has an active
    Sheets filter that hides ~90% of rows from the CSV export."""
    rows = fetch_sheet_objects_xlsx(SHEET_IDS["daily"], "raw")
    out = []
    for r in rows:
        platform = platform_of(r.get('Source'))
        if not platform:
            continue
        if platform == 'GMB':
            sentiment = gmb_sentiment_from_recommendation(get_matching_row_value(r, ['Recommendation']))
            if not sentiment:
                sentiment = (r.get('Final Sentiment') or '').strip().lower()
        else:
            sentiment = (r.get('Final Sentiment') or '').strip().lower()
        if sentiment not in ('positive', 'negative', 'neutral'):
            continue
        out.append({
            "date": parse_date_value(r.get('Case Start Date')),
            "sentiment": sentiment,
            "project": normalize_gmb_project(r.get('Channel Name')),
            "platform": platform,
        })
    return out


# ---------- Window aggregation ----------
def empty_counts():
    return {"positive": 0, "negative": 0, "neutral": 0}


def tally(counts, sentiment):
    if sentiment in counts:
        counts[sentiment] += 1


def reddit_counts_for_window(rows, start, end):
    counts = empty_counts()
    for r in rows:
        d = get_row_date(r)
        if not d or not (start <= d <= end):
            continue
        counts["positive"] += num_or(get_matching_row_value(r, ['Total Positive comments']), 0)
        counts["negative"] += num_or(get_matching_row_value(r, ['Total Nagative comments', 'Total Negative comments']), 0)
        counts["neutral"] += num_or(get_matching_row_value(r, ['Total Neutral comments']), 0)
    return {k: round(v) for k, v in counts.items()}


def gmb_counts_for_window(social_rows, start, end):
    counts = empty_counts()
    for r in social_rows:
        if r["platform"] != "GMB" or not r["date"] or not (start <= r["date"] <= end):
            continue
        tally(counts, r["sentiment"])
    return counts


def social_counts_for_window(social_rows, start, end):
    counts = empty_counts()
    for r in social_rows:
        if r["platform"] == "GMB" or not r["date"] or not (start <= r["date"] <= end):
            continue
        tally(counts, r["sentiment"])
    return counts


def platform_counts_for_window(social_rows, platform, start, end):
    """Single-platform slice of social_counts_for_window — feeds the Instagram/Facebook/
    LinkedIn mini-pies on the Social tab."""
    counts = empty_counts()
    for r in social_rows:
        if r["platform"] != platform or not r["date"] or not (start <= r["date"] <= end):
            continue
        tally(counts, r["sentiment"])
    return counts


def overall_counts(reddit, gmb, social):
    return {k: reddit[k] + gmb[k] + social[k] for k in ("positive", "negative", "neutral")}


# ---------- Bucket enumeration ----------
def complete_weeks(today):
    """Every Monday-Sunday week from WEEK1_START through the last one that has fully
    elapsed before today — the in-progress week is deliberately excluded."""
    weeks = []
    monday = WEEK1_START
    while True:
        sunday = monday + timedelta(days=6)
        if sunday >= today:
            break
        weeks.append((monday, sunday))
        monday += timedelta(days=7)
    return weeks


def complete_months(today):
    months = []
    y, m = WEEK1_START.year, WEEK1_START.month
    while date(y, m, 1) < date(today.year, today.month, 1):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def month_bounds(month_key):
    y, m = (int(x) for x in month_key.split('-'))
    start = date(y, m, 1)
    end = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1) - timedelta(days=1)
    return start, end


def main():
    print("Fetching Reddit & Quora Content Plan…")
    reddit_rows = load_reddit_rows()
    quora_counts = load_quora_sentiment()
    print(f"  {len(reddit_rows)} reddit rows (New Seeds + Existing Threads)")

    print("Fetching Sumadhura daily report ('raw' tab, XLSX)…")
    social_rows = load_social_rows()
    print(f"  {len(social_rows)} dated GMB/Instagram/Facebook/LinkedIn rows")

    today = date.today()
    weeks = complete_weeks(today)
    months = complete_months(today)
    print(f"Today: {today}. Freezing {len(weeks)} complete week(s), {len(months)} complete month(s).")

    sentiment_counts = {"weekly": {}, "monthly": {}}

    def bucket_for(start, end):
        reddit = reddit_counts_for_window(reddit_rows, start, end)
        gmb = gmb_counts_for_window(social_rows, start, end)
        social = social_counts_for_window(social_rows, start, end)
        overall = overall_counts(reddit, gmb, social)
        return {
            "GMB": gmb, "Reddit": reddit, "Quora": quora_counts,
            "Social": social, "Overall": overall,
            "Instagram": platform_counts_for_window(social_rows, "Instagram", start, end),
            "Facebook": platform_counts_for_window(social_rows, "Facebook", start, end),
            "LinkedIn": platform_counts_for_window(social_rows, "LinkedIn", start, end),
        }

    for monday, sunday in weeks:
        key = monday.isoformat()
        sentiment_counts["weekly"][key] = bucket_for(monday, sunday)
        print(f"  week {key} ({monday}–{sunday}): "
              f"GMB={sentiment_counts['weekly'][key]['GMB']} "
              f"Reddit={sentiment_counts['weekly'][key]['Reddit']}")

    for month_key in months:
        start, end = month_bounds(month_key)
        sentiment_counts["monthly"][month_key] = bucket_for(start, end)
        print(f"  month {month_key} ({start}–{end}): "
              f"GMB={sentiment_counts['monthly'][month_key]['GMB']} "
              f"Social={sentiment_counts['monthly'][month_key]['Social']}")

    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    cache["sentimentCounts"] = sentiment_counts
    cache["generated_at"] = datetime.now().astimezone().isoformat()
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote sentimentCounts into {CACHE_PATH}")


if __name__ == "__main__":
    sys.exit(main())
