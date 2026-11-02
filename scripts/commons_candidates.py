#!/usr/bin/env python3
"""Collect free-licensed photo candidates from Wikimedia Commons.

Runs a few File-namespace searches, reads licence metadata for each hit, sorts
every file into OK / SA / NO, downloads 800px thumbnails for OK and SA files only,
and writes commons-candidates/candidates.json plus a README.md overview.

Standard library only. Output folder: commons-candidates/ at the repo root.
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "HoopsMatic-asset-bot/1.0 (hoopsmatic@hoopsmatic.com)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "commons-candidates")

SEARCHES = [
    ("lebron", "LeBron James Lakers"),
    ("curry", "Stephen Curry Warriors"),
    ("warriors", "Golden State Warriors 2016"),
]
LIMIT = 50
THUMB_WIDTH = 800
META_FIELDS = ["LicenseShortName", "LicenseUrl", "Artist", "Credit",
               "DateTimeOriginal", "Restrictions", "ImageDescription"]


def http_get(url, retries=7):
    """GET with backoff. Commons answers 429 when busy; honour Retry-After when it sends one."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == retries - 1 or (code and code < 500 and code != 429):
                raise
            wait = min(120, 5 * 2 ** attempt)
            retry_after = getattr(e, "headers", None) and e.headers.get("Retry-After")
            if retry_after and str(retry_after).isdigit():
                wait = min(300, max(wait, int(retry_after)))
            print(f"  retry in {wait}s after: {e}")
            time.sleep(wait)


def api(params):
    params = dict(params, format="json", formatversion="2")
    return json.loads(http_get(API + "?" + urllib.parse.urlencode(params)))


def plain(value, max_len=None):
    """extmetadata values are HTML snippets; turn them into one line of plain text."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def verdict(license_name):
    """OK = CC0 / public domain / CC BY (no SA). SA = CC BY-SA. NO = everything else."""
    s = plain(license_name).lower()
    if not s:
        return "NO"
    if s.startswith("cc0") or "public domain" in s or re.match(r"^pd(\b|-)", s):
        return "OK"
    tokens = re.split(r"[\s\-]+", s)
    if tokens[:2] == ["cc", "by"]:
        rest = tokens[2:]
        if "nc" in rest or "nd" in rest:
            return "NO"
        if rest and rest[0] == "sa":
            return "SA"
        # Remaining tokens must be a version number and/or jurisdiction code (e.g. "2.0", "3.0 us")
        if all(re.match(r"^(\d+(\.\d+)?|[a-z]{2,3})$", t) for t in rest):
            return "OK"
    return "NO"


def search(query):
    """Return pages in search-rank order, merging imageinfo across API continuations."""
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(LIMIT),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": str(THUMB_WIDTH),
        "iiextmetadatafilter": "|".join(META_FIELDS),
    }
    pages = {}
    cont = {}
    while True:
        data = api({**params, **cont})
        for p in data.get("query", {}).get("pages", []):
            cur = pages.setdefault(p["pageid"], {"title": p["title"], "index": p.get("index", 999)})
            if p.get("imageinfo"):
                cur["imageinfo"] = p["imageinfo"]
        cont = data.get("continue", {})
        # Follow imageinfo continuation only (pass the whole dict back so the generator holds
        # its batch). A continue without iicontinue just offers the next 50 search hits: stop.
        if "iicontinue" not in cont:
            break
    return sorted(pages.values(), key=lambda x: x["index"])


def safe_name(title):
    name = title.split(":", 1)[-1]
    name = os.path.splitext(name)[0]
    name = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
    return name[:80] or "file"


def md_cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def main():
    os.makedirs(OUT, exist_ok=True)
    candidates = []
    first_download = True
    for key, query in SEARCHES:
        print(f"Search {key}: {query!r}")
        folder = os.path.join(OUT, key)
        os.makedirs(folder, exist_ok=True)
        pages = search(query)
        n = 0
        for page in pages:
            info = (page.get("imageinfo") or [None])[0]
            if not info or info.get("mime") not in ("image/jpeg", "image/png"):
                continue
            n += 1
            meta = info.get("extmetadata", {})
            mv = lambda k: (meta.get(k) or {}).get("value", "")
            lic = plain(mv("LicenseShortName"))
            v = verdict(lic)
            row = {
                "search": key,
                "verdict": v,
                "title": page["title"],
                "page_url": info.get("descriptionurl", ""),
                "original_url": info.get("url", ""),
                "width": info.get("width"),
                "height": info.get("height"),
                "license": lic,
                "license_url": plain(mv("LicenseUrl")),
                "artist": plain(mv("Artist")),
                "credit": plain(mv("Credit")),
                "date": plain(mv("DateTimeOriginal")),
                "restrictions": plain(mv("Restrictions")),
                "description": plain(mv("ImageDescription"), 300),
                "thumb_path": None,
            }
            thumb = info.get("thumburl")
            if v in ("OK", "SA") and thumb:
                # Thumbnails keep the source format, so PNGs are saved as .png, not .jpg.
                ext = ".png" if info.get("mime") == "image/png" else ".jpg"
                rel = f"commons-candidates/{key}/{n:02d}-{safe_name(page['title'])}{ext}"
                dest = os.path.join(ROOT, rel)
                if not os.path.exists(dest):
                    if not first_download:
                        time.sleep(1)  # be polite to Commons
                    first_download = False
                    try:
                        data = http_get(thumb, retries=5)
                        with open(dest, "wb") as f:
                            f.write(data)
                    except Exception as e:
                        print(f"  download failed for {page['title']}: {e}")
                        rel = None
                if rel:
                    row["thumb_path"] = rel
            candidates.append(row)
            print(f"  {n:02d} {v:2} {lic or '(no licence)'}  {page['title']}")

    with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
        f.write("\n")

    lines = ["# Wikimedia Commons candidates", "",
             "Generated by `scripts/commons_candidates.py`. Verdicts: **OK** = CC0, public domain "
             "or CC BY (no share-alike); **SA** = CC BY-SA; **NO** = anything else (not downloaded). "
             "Always check the file page before use and credit the artist as the licence requires.", ""]
    for key, query in SEARCHES:
        rows = [c for c in candidates if c["search"] == key]
        counts = {k: sum(1 for c in rows if c["verdict"] == k) for k in ("OK", "SA", "NO")}
        lines += [f"## {key}: \"{query}\"", "",
                  f"OK {counts['OK']} · SA {counts['SA']} · NO {counts['NO']}", "",
                  "| Thumbnail | Title | Verdict | License | Artist | Date | Size |",
                  "|---|---|---|---|---|---|---|"]
        for c in rows:
            thumb = c["thumb_path"] or ""
            if thumb:
                thumb = f"[{os.path.basename(thumb)}]({thumb.split('/', 1)[1]})"
            title = f"[{md_cell(c['title'].split(':', 1)[-1])}]({c['page_url']})"
            lines.append("| " + " | ".join([
                thumb, title, c["verdict"], md_cell(c["license"]),
                md_cell(c["artist"][:60]), md_cell(c["date"][:20]),
                f"{c['width']} x {c['height']}"]) + " |")
        lines.append("")
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(candidates)} candidates")


if __name__ == "__main__":
    main()
