#!/usr/bin/env python3
"""Asia Series Poker Tour(aspt.world)のシリーズ日程を取得し、共通形式の JSON にする。

公式の大会ページ /en/events/<slug>/ は静的 HTML で、1大会が1つの
<article class="schedule-item" data-day="YYYY-MM-DD" data-search="名前 ゲーム #番号 金額 …"> になっている。
時刻は現地時間(韓国)。保証額・スタック・レベル時間は載っていない。

    python3 scripts/fetch_aspt_series.py aspt-korea-2027 tmp/aspt-korea-2027/events.json \
        --title "ASPT Korea 2027" --venue "Paradise City（仁川）"
"""
import argparse
import datetime as dt
import html
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://aspt.world/en/events"
ITEM = re.compile(r'<article class="schedule-item" data-day="(\d{4}-\d{2}-\d{2})" data-search="([^"]*)">(.*?)</article>', re.S)
GAME = {"NLH": "NLH", "PLO": "PLO", "MIX": "Mixed", "DRAW": "Draw", "STUD": "Stud"}


def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).split()


def parse(page: str, url: str) -> list:
    evs = []
    for day, search, body in ITEM.findall(page):
        start = re.search(r"<time>([\d:]+)</time>", body)
        no = re.search(r'class="event-number">#?([^<]*)<', body)
        name = re.search(r"<h3>(.*?)<span class=\"flags\"", body, re.S)
        flags = re.findall(r'class="flag (\w+)"', body)
        buy = re.search(r'class="buyin"><small>[^<]*</small>([^<]*)<', body)
        late = re.search(r"Late Reg ([\d:]+)", body)
        tokens = html.unescape(search).split()
        game = next((GAME[t] for t in tokens if t in GAME), "")
        nm = " ".join(text(name.group(1))) if name else ""
        amount = buy.group(1).strip() if buy else ""
        cont = bool(re.search(r"Day ?[2-9]|Final", nm)) and not amount.startswith("₩")
        evs.append({
            "date": day, "start": start.group(1) if start else "", "late": late.group(1) if late else "",
            "eventNo": (no.group(1).strip() if no else ""), "name": nm,
            "buyIn": int(re.sub(r"\D", "", amount)) if amount.startswith("₩") else None,
            "buyInNote": "" if amount.startswith("₩") else amount,
            "gtd": None, "isSatellite": "sat" in flags or "Satellite" in nm, "isContinuation": cont,
            "isMain": "main" in flags, "game": game, "url": url, "stack": None, "levelMin": None,
        })
    return sorted(evs, key=lambda e: (e["date"], e["start"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--venue", required=True)
    a = ap.parse_args()
    url = f"{BASE}/{a.slug}/"
    page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read().decode("utf-8")
    evs = parse(page, url)
    data = {"series": {"title": a.title, "venue": a.venue, "currency": "KRW", "sourceUrl": url,
                       "sourceLabel": "ASPT 公式", "fetchedAt": dt.date.today().isoformat()},
            "events": evs}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{a.out}: {len(evs)} rows")


if __name__ == "__main__":
    main()
