#!/usr/bin/env python3
"""Gods of Poker(godsofpoker.com)のシリーズ日程を取得し、共通形式の JSON にする。

公式は SvelteKit 製で、ページの HTML にイベント一覧がインラインの JS オブジェクト
(`{kholdem_id:"…",date:…,title:…,startTime:…}`)として入っている。時刻は現地時刻
(timezone フィールド、韓国開催なら Asia/Seoul)。
同じイベントが2回ずつ出てくるので kholdem_id で重複を除き、シリーズ全体の集計行
(isSummary:true)は落とす。

    python3 scripts/fetch_gop_series.py incheon-2026-ii tmp/gop-incheon-2026-ii/events.json \
        --venue "Paradise City（仁川）"
"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://godsofpoker.com"


def s_(p: str, k: str):
    m = re.search(r"\b" + k + r':"([^"]*)"', p)
    return m.group(1) if m else None


def n_(p: str, k: str):
    m = re.search(r"\b" + k + r":(-?[\d.]+)", p)
    return float(m.group(1)) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="例: incheon-2026-ii")
    ap.add_argument("out")
    ap.add_argument("--venue", required=True)
    args = ap.parse_args()

    url = f"{BASE}/series/{args.slug}"
    page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                  timeout=20).read().decode("utf-8", "replace")
    title = (re.search(r"<title>([^<]*)", page) or [None, args.slug])[1].replace(" - Gods of Poker", "")

    seen, events = set(), []
    for p in page.split('{kholdem_id:"')[1:]:
        eid = p[:36]
        head = p[:2500]  # 次のイベントに入る前の範囲だけを見る
        if eid in seen or "isSummary:true" in head:
            continue
        seen.add(eid)
        start, close = s_(head, "startTime"), s_(head, "regClose")
        name = (s_(head, "title") or "").strip()
        if not start or not name:
            continue
        cont = bool(re.search(r"\bDay\s*[2-9]\b|Final Day", name, re.I))
        # lateRegLevel はどのイベントも 3 で、regClose までの実時間と合わない。締切は時刻だけ出す
        late = ""
        if close and not cont:
            cd = dt.datetime.fromisoformat(close)
            late = (f"{cd:%H:%M}" if cd.date().isoformat() == start[:10] else f"{cd.month}/{cd.day} {cd:%H:%M}")
        total, contrib = n_(head, "totalBuyin"), n_(head, "buyInPrizePoolContrib")
        note = ""
        if total and contrib and total > contrib:
            note = f"₩{int(contrib):,} + ₩{int(total - contrib):,}"
        gtd = n_(head, "guaranteedAmount")
        events.append({
            "date": start[:10], "start": start[11:16], "late": late,
            "eventNo": s_(head, "eventNumber") or "", "name": name,
            "buyIn": None if cont else (int(total) if total else None), "buyInNote": note,
            "gtd": int(gtd) if gtd else None,
            "isSatellite": "satellite" in name.lower(), "isContinuation": cont,
            "isMain": bool(re.search(r"\bMain Event\b", name)) and "mini" not in name.lower(),
            "officialGame": "", "url": f"{BASE}/event/{eid}",
            "stack": int(n_(head, "startingStack") or 0) or None,
            # status.level.totalMinutes はメインの各 Flight でも Day2 の 60 分が入っている。
            # 大会名に「(40 Mins …)」と書いてあればそちらを優先する
            "levelMin": int((re.search(r"\((\d+) Mins", name) or [None, 0])[1] or n_(head, "totalMinutes") or 0) or None,
        })
    events.sort(key=lambda e: (e["date"], e["start"], e["eventNo"]))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    payload = {
        "series": {"title": f"Gods of Poker Incheon「{title}」" if "incheon" in args.slug else title,
                   "venue": args.venue, "currency": "KRW", "sourceUrl": url,
                   "sourceLabel": "Gods of Poker 公式", "fetchedAt": dt.date.today().isoformat(),
                   "lateRegNote": "公式の regClose(登録締切の時刻)。公式の締切レベル番号は実時間と合わないため表示しない"},
        "events": events,
    }
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{args.out}: {len(events)} rows (unique {len(seen)})  {title}")


if __name__ == "__main__":
    main()
