#!/usr/bin/env python3
"""WPT のシリーズ日程を PokerNews の記事の表から取得し、共通形式の JSON にする。

worldpokertour.com は Cloudflare で自動取得できない(403)ため、PokerNews が
公開している日程表(Date / Time / # / Event / Buy-In / Guarantee)を使う。
レジ締切は記事に載っていないので空欄になる。

    python3 scripts/fetch_wpt_pokernews.py <記事URL> tmp/wpt-seoul-2026/events.json \
        --title "WPT Seoul 2026" --venue "INSPIRE Entertainment Resort（仁川）" --year 2026
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def money(s: str):
    nums = re.findall(r"[\d,]{4,}", s or "")
    return int(nums[0].replace(",", "")) if nums else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--venue", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--main-no", default="", help="メインイベントの Event #(例: 27)")
    args = ap.parse_args()

    req = urllib.request.Request(args.url, headers={"User-Agent": UA})
    page = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    tables = re.findall(r"<table.*?</table>", page, re.S)
    if not tables:
        raise SystemExit("記事に日程表が見つからない")

    events = []
    for tr in re.findall(r"<tr.*?</tr>", tables[0], re.S)[1:]:
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip()
             for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if len(c) < 6:
            continue
        date_s, time_s, no, name, buy_s, gtd_s = c[:6]
        m = re.match(r"\w{3}\s+(\d{1,2})\s+(\w{3})", date_s)
        if not m:
            continue
        d = dt.date(args.year, MONTHS[m.group(2)], int(m.group(1)))
        cont = bool(re.search(r"\bDay\s*[2-9]\b|Final", name, re.I))
        events.append({
            "date": d.isoformat(), "start": time_s, "late": "",
            "eventNo": "" if no.upper() == "SAT" else no, "name": name,
            "buyIn": money(buy_s), "buyInNote": "", "gtd": money(gtd_s),
            "isSatellite": no.upper() == "SAT" or "satellite" in name.lower(),
            "isContinuation": cont, "isMain": bool(args.main_no) and no == args.main_no,
            "officialGame": "", "url": args.url, "stack": None, "levelMin": None,
        })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    payload = {
        "series": {"title": args.title, "venue": args.venue, "currency": "KRW",
                   "sourceUrl": args.url, "sourceLabel": "PokerNews（公式サイトは自動取得不可のため）",
                   "fetchedAt": dt.date.today().isoformat(),
                   "lateRegNote": "レジ締切は出典に載っていないため空欄"},
        "events": events,
    }
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{args.out}: {len(events)} rows")


if __name__ == "__main__":
    main()
