#!/usr/bin/env python3
"""
Build a podcast-style RSS feed for https://gpww.differentdrum.ca/

How it works
  1. Fetch the home page and collect every weekly episode link (/YYYY/MM/DD/slug/).
  2. For episodes not seen before, fetch the episode page and pull out the mp3 URL
     from the <audio> player (the date comes from the URL).
  3. Remember what it found in episodes.json, so later runs only fetch NEW pages.
  4. Write docs/feed.xml (newest episode first).

Standard library only. Set FEED_URL to the public address of feed.xml (optional,
used for the feed's self-link).
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

SITE = "https://gpww.differentdrum.ca"
CACHE_FILE = Path("episodes.json")
FEED_FILE = Path("docs/feed.xml")
FEED_URL = os.environ.get("FEED_URL", "")
USER_AGENT = "gpww-personal-rss/1.0 (personal podcast feed; checks the site about once a day)"
DELAY_SECONDS = 1.0  # pause between requests to be gentle on the site

CHANNEL_TITLE = "Gilles Peterson Worldwide (archive)"
CHANNEL_DESC = "Archived Gilles Peterson Worldwide radio shows (BBC 6 Music) for listening back."
CHANNEL_IMAGE = SITE + "/assets/images/gilles-peterson-bbc6music-sqr-bw-dithered-pixel2.jpg"

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)


def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read() if method == "GET" else b""
        return body, resp.headers


# ---------- parsing ----------

EPISODE_LINK = re.compile(r'href="(/(\d{4})/(\d{2})/(\d{2})/[^"/]+/)"')


def parse_index(page_html):
    """Return [(path, 'YYYY-MM-DD'), ...] for every episode link, deduplicated."""
    seen, out = set(), []
    for path, y, m, d in EPISODE_LINK.findall(page_html):
        if path not in seen:
            seen.add(path)
            out.append((path, f"{y}-{m}-{d}"))
    return out


def parse_episode(page_html, page_url):
    """Return (title, mp3_url) from an episode page, or (title, None) if no mp3."""
    # The page contains an old player inside an HTML comment; ignore commented-out markup.
    live = re.sub(r"<!--.*?-->", "", page_html, flags=re.S)
    m = re.search(r'<audio\b[^>]*?\bsrc="([^"]+?\.mp3[^"]*)"', live, flags=re.S | re.I)
    mp3 = urljoin(page_url, html.unescape(m.group(1))) if m else None
    t = re.search(r"<title>(.*?)</title>", live, flags=re.S | re.I)
    title = html.unescape(t.group(1)).strip() if t else ""
    title = re.sub(r"\s*-\s*gpww\s*$", "", title)
    return title, mp3


# ---------- feed building ----------

def build_feed(episodes):
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = CHANNEL_TITLE
    ET.SubElement(ch, "link").text = SITE + "/"
    ET.SubElement(ch, "description").text = CHANNEL_DESC
    ET.SubElement(ch, "language").text = "en"
    if FEED_URL:
        ET.SubElement(ch, f"{{{ATOM}}}link", {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"})
    ET.SubElement(ch, f"{{{ITUNES}}}author").text = "Gilles Peterson"
    ET.SubElement(ch, f"{{{ITUNES}}}image", {"href": CHANNEL_IMAGE})
    ET.SubElement(ch, f"{{{ITUNES}}}category", {"text": "Music"})
    ET.SubElement(ch, f"{{{ITUNES}}}explicit").text = "false"

    items = sorted(episodes.values(), key=lambda e: e["date"], reverse=True)

    def pubdate(iso):
        # noon UTC so the date doesn't shift in any timezone
        return format_datetime(datetime.fromisoformat(iso).replace(hour=12, tzinfo=timezone.utc))

    # lastBuildDate follows the newest episode, so the file only changes when there is a new one
    if items:
        ET.SubElement(ch, "lastBuildDate").text = pubdate(items[0]["date"])

    for e in items:
        it = ET.SubElement(ch, "item")
        ET.SubElement(it, "title").text = f'{e["date"]} - {e["title"]}'
        ET.SubElement(it, "link").text = e["page_url"]
        ET.SubElement(it, "guid", {"isPermaLink": "true"}).text = e["page_url"]
        ET.SubElement(it, "pubDate").text = pubdate(e["date"])
        ET.SubElement(it, "description").text = f'Gilles Peterson Worldwide, BBC 6 Music - broadcast {e["date"]}.'
        ET.SubElement(it, "enclosure", {
            "url": e["mp3"],
            "length": str(e.get("length", 0)),
            "type": e.get("type", "audio/mpeg"),
        })
        ET.SubElement(it, f"{{{ITUNES}}}image", {"href": CHANNEL_IMAGE})

    ET.indent(rss)
    return ET.ElementTree(rss)


# ---------- main ----------

def main():
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

    body, _ = fetch(SITE + "/")  # if this fails the run fails, so you get a notification
    found = parse_index(body.decode("utf-8", "replace"))
    if not found:
        sys.exit("No episode links found on the home page - has the site layout changed?")

    new = [(p, d) for p, d in found if p not in cache]
    print(f"{len(found)} episodes on site, {len(new)} new")

    for path, date in new:
        url = SITE + path
        time.sleep(DELAY_SECONDS)
        try:
            page, _ = fetch(url)
            title, mp3 = parse_episode(page.decode("utf-8", "replace"), url)
        except Exception as exc:
            print(f"  skip {path}: {exc}")
            continue
        if not mp3:
            print(f"  skip {path}: no mp3 found yet (will retry next run)")
            continue
        length, ctype = 0, "audio/mpeg"
        try:
            time.sleep(DELAY_SECONDS)
            _, hdrs = fetch(mp3, method="HEAD")
            length = int(hdrs.get("Content-Length") or 0)
            ctype = hdrs.get("Content-Type") or ctype
        except Exception as exc:
            print(f"  could not read mp3 size for {path}: {exc}")
        cache[path] = {"date": date, "title": title, "page_url": url,
                       "mp3": mp3, "length": length, "type": ctype}
        print(f"  added {date}: {mp3}")

    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    build_feed(cache).write(FEED_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {FEED_FILE} with {len(cache)} episodes")


if __name__ == "__main__":
    main()
