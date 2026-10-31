#!/usr/bin/env python3
"""WPT のシリーズ日程を YY Poker Club アプリ(会場 INSPIRE の公式アプリ)の公開 API から取得し、
共通形式の JSON にする。

PokerNews の記事表と違い、レジ締切(時刻・レベル)・スターティングスタック・1レベルの分数・
保証額まで入っている。API は認証不要の JSON:

    https://app.theyypoker.com/api/public/events/<event_id>/schedule

    python3 scripts/fetch_wpt_yy.py wpt-seoul-2026 tmp/wpt-seoul-2026/events.json \
        --title "WPT Seoul 2026" --venue "INSPIRE Entertainment Resort（仁川）" --main-no 27
"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request

API = "https://app.theyypoker.com/api/public/events/{}/schedule"
APP = "https://app.theyypoker.com/?lang=ja"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def local_hhmm(iso: str, tz_hours: int) -> str:
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")) + dt.timedelta(hours=tz_hours)
    return f"{t:%H:%M}"


def clean_title(t: str) -> str:
    # 保証額はカードに別欄で出るので、名前からは "(KRW 100 Million GTD)" 等を外す
    t = re.sub(r"\s*\((?:KRW|₩)[^)]*GTD[^)]*\)", "", t)
    t = re.sub(r"\s*\(KRW [^,)]*GTD,\s*", " (", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def stack_and_clock(details: str):
    """"Starting stack 40K · 30-min levels" → (40000, 30, "30")。25/30 のような表記は最初の値を目安に使う"""
    stack = clock = None
    clock_text = ""
    m = re.search(r"Starting stack\s+([\d.]+)\s*([KM]?)", details or "", re.I)
    if m:
        stack = int(float(m.group(1)) * {"": 1, "K": 1000, "M": 1000000}[m.group(2).upper()])
    m = re.search(r"([\d/]+)-min levels", details or "", re.I)
    if m:
        clock_text = m.group(1)
        clock = int(clock_text.split("/")[0])
    return stack, clock, clock_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("event_id", help="YY の event_id(例: wpt-seoul-2026)")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--venue", required=True)
    ap.add_argument("--main-no", default="", help="メインイベントの Event #(例: 27)")
    ap.add_argument("--input", help="API の代わりに保存済みの JSON を読む(確認用)")
    args = ap.parse_args()

    if args.input:
        data = json.load(open(args.input, encoding="utf-8"))
    else:
        req = urllib.request.Request(API.format(args.event_id), headers={"User-Agent": UA, "Accept": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    tz = 9 if data.get("timezone", "Asia/Seoul") in ("Asia/Seoul", "Asia/Tokyo") else 0
    sessions = data.get("sessions") or []
    if not sessions:
        raise SystemExit("YY の日程が空")

    events = []
    for s in sorted(sessions, key=lambda x: (x["local_date"], x["local_time"], x.get("event_number") or 999)):
        no = str(s["event_number"]) if s.get("event_number") else ""
        flight = s.get("flight") or ""
        name = clean_title(s["title"]) + (f" {flight}" if flight else "")
        lr = s.get("late_registration") or {}
        stack, clock, clock_text = stack_and_clock(s.get("details_text") or "")
        notes = list(s.get("notes") or [])
        if not lr.get("closes_at") and not s.get("continuation") and no:
            # Day 1 で締め切らず翌日のフライトまで登録できる大会(High Roller 等)は、その締切を書いておく
            nxt = next((x for x in sessions if x.get("event_number") == s["event_number"] and x is not s
                        and (x.get("late_registration") or {}).get("closes_at")), None)
            if nxt:
                nl = nxt["late_registration"]
                lv = f"（Lv {nl['level']}）" if nl.get("level") else ""
                notes.insert(0, f"レジは {nxt.get('flight') or nxt['local_date']}（{nxt['local_date'][5:].replace('-', '/')}）の "
                                f"{local_hhmm(nl['closes_at'], tz)}{lv} まで")
        if "/" in clock_text:
            notes.insert(0, f"レベルは {clock_text} 分（表は {clock} 分で計算した目安）")
        events.append({
            "date": s["local_date"], "start": s["local_time"],
            "late": local_hhmm(lr["closes_at"], tz) if lr.get("closes_at") else "",
            "lateLv": lr.get("level"),
            "eventNo": no, "name": name,
            "buyIn": s.get("buy_in_krw"), "buyInNote": " / ".join(notes), "gtd": s.get("guarantee_krw"),
            "isSatellite": s.get("kind") == "satellite" or "satellite" in s["title"].lower(),
            "isContinuation": bool(s.get("continuation")),
            "isMain": bool(args.main_no) and no == args.main_no,
            "officialGame": s.get("game") or "", "url": APP, "stack": stack, "levelMin": clock,
        })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    src = data.get("source") or {}
    payload = {
        "series": {"title": args.title, "venue": args.venue, "currency": "KRW",
                   "sourceUrl": APP, "sourceLabel": "YY Poker Club アプリ（INSPIRE 公式）",
                   "fetchedAt": dt.date.today().isoformat(),
                   "sourceRevision": src.get("revision"), "sourcePublishedAt": src.get("published_at"),
                   "lateRegNote": "レジ締切は YY アプリの時刻・レベル"},
        "events": events,
    }
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{args.out}: {len(events)} rows")


if __name__ == "__main__":
    main()
