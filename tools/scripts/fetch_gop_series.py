#!/usr/bin/env python3
"""Gods of Poker(godsofpoker.com)のシリーズ日程を取得し、共通形式の JSON にする。

公式は SvelteKit 製で、ページの HTML にイベント一覧がインラインの JS オブジェクト
(`{kholdem_id:"…",date:…,title:…,startTime:…}`)として入っている。時刻は現地時刻
(timezone フィールド、韓国開催なら Asia/Seoul)。
同じイベントが2回ずつ出てくるので kholdem_id で重複を除き、シリーズ全体の集計行
(isSummary:true)は落とす。

ストラクチャー(ブラインド・休憩)はシリーズページに無いので、イベントごとの
/event/<id> を取りに行く(levels 配列。type:2 が休憩)。
エントリー数・残り人数・進行中のレベルはシリーズページにある(live)。
開催中はこれだけを tools/live.py が15分ごとに取り直す。

    python3 scripts/fetch_gop_series.py incheon-2026-ii tmp/gop-incheon-2026-ii/events.json \
        --venue "Paradise City（仁川）"
"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://godsofpoker.com"


def s_(p: str, k: str):
    m = re.search(r"\b" + k + r':"([^"]*)"', p)
    return m.group(1) if m else None


def n_(p: str, k: str):
    m = re.search(r"\b" + k + r":(-?[\d.]+)", p)
    return float(m.group(1)) if m else None


def get(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                  timeout=20).read().decode("utf-8", "replace")


def series_blocks(page: str) -> dict:
    """kholdem_id → そのイベントの範囲の文字列(重複・集計行は除く)"""
    out = {}
    for p in page.split('{kholdem_id:"')[1:]:
        eid, head = p[:36], p[:2500]  # 次のイベントに入る前の範囲だけを見る
        if eid not in out and "isSummary:true" not in head:
            out[eid] = head
    return out


def live_of(head: str) -> dict:
    """エントリー数・残り人数・平均スタック・進行状況。始まっていなければ空"""
    entries = int(n_(head, "totalEntries") or 0)
    ph = re.search(r'phase:\{code:"(\w+)",label:"([^"]*)"', head)
    lv = re.search(r"status:\{gameInProgress:(\w+),paused:(\w+).*?level:\{id:\d+,elapsed:(\d+),totalMinutes:(\d+),index:(\d+)",
                   head)
    if not entries and not (lv and lv.group(1) == "true"):
        return {}
    return {"entries": entries, "players": int(n_(head, "totalPlayers") or 0),
            "avg": int(n_(head, "averageChipCount") or 0),
            "phase": ph.group(2) if ph else "", "phaseCode": ph.group(1) if ph else "",
            "running": bool(lv and lv.group(1) == "true"), "paused": bool(lv and lv.group(2) == "true"),
            "lv": int(lv.group(5)) if lv else None,
            "elapsed": int(lv.group(3)) if lv else 0, "lvMin": int(lv.group(4)) if lv else None}


def structure(eid: str):
    """イベントページの levels を [レベル番号(休憩は0), SB, BB, ante, 分, 開始 HH:MM] の配列に"""
    try:
        page = get(f"{BASE}/event/{eid}")
    except Exception:  # noqa: BLE001
        return None, None
    i = page.find(f'kholdem_id:"{eid}"')
    j = page.find("levels:[", i)
    if i < 0 or j < 0:
        return None, None
    body = page[j:page.find("]", j)]
    rows = []
    for m in re.finditer(r"\{id:\d+,index:(\d+),type:(\d+),smallBlind:(\d+),bigBlind:(\d+),ante:(\d+)"
                         r".*?minutes:(\d+).*?startTime:\"[\d-]+T(\d\d:\d\d)", body):
        idx, typ, sb, bb, ante, mins, start = m.groups()
        rows.append([0 if typ == "2" else int(idx), int(sb), int(bb), int(ante), int(mins), start])
    return rows or None, int(n_(page[i:i + 3000], "lateRegLevel") or 0) or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="例: incheon-2026-ii")
    ap.add_argument("out")
    ap.add_argument("--venue", required=True)
    args = ap.parse_args()

    url = f"{BASE}/series/{args.slug}"
    page = get(url)
    title = (re.search(r"<title>([^<]*)", page) or [None, args.slug])[1].replace(" - Gods of Poker", "")

    blocks = series_blocks(page)
    with ThreadPoolExecutor(8) as ex:
        structs = dict(zip(blocks, ex.map(structure, blocks)))

    events = []
    for eid, head in blocks.items():
        start, close = s_(head, "startTime"), s_(head, "regClose")
        name = (s_(head, "title") or "").strip()
        if not start or not name:
            continue
        cont = bool(re.search(r"\bDay\s*[2-9]\b|Final Day", name, re.I))
        levels, late_lv = structs.get(eid) or (None, None)
        late = ""
        if close and not cont:
            cd = dt.datetime.fromisoformat(close)
            late = (f"{cd:%H:%M}" if cd.date().isoformat() == start[:10] else f"{cd.month}/{cd.day} {cd:%H:%M}")
        total, contrib = n_(head, "totalBuyin"), n_(head, "buyInPrizePoolContrib")
        note = ""
        if total and contrib and total > contrib:
            note = f"₩{int(contrib):,} + ₩{int(total - contrib):,}"
        gtd = n_(head, "guaranteedAmount")
        # 1レベルの分数はストラクチャーの最初の通常レベルが正。無ければ大会名の「(40 Mins …)」
        first = next((r[4] for r in levels or [] if r[0]), None)
        events.append({
            "date": start[:10], "start": start[11:16], "late": late,
            "lateLv": None if cont else late_lv,
            "eventNo": s_(head, "eventNumber") or "", "name": name,
            "buyIn": None if cont else (int(total) if total else None), "buyInNote": note,
            "gtd": int(gtd) if gtd else None,
            "isSatellite": "satellite" in name.lower(), "isContinuation": cont,
            "isMain": bool(re.search(r"\bMain Event\b", name)) and "mini" not in name.lower(),
            "officialGame": "", "url": f"{BASE}/event/{eid}", "liveId": eid,
            "stack": int(n_(head, "startingStack") or 0) or None,
            "levelMin": first or int((re.search(r"\((\d+) Mins", name) or [None, 0])[1] or 0) or None,
            "levels": levels, "live": live_of(head),
        })
    events.sort(key=lambda e: (e["date"], e["start"], e["eventNo"]))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    payload = {
        "series": {"title": f"Gods of Poker Incheon「{title}」" if "incheon" in args.slug else title,
                   "venue": args.venue, "currency": "KRW", "sourceUrl": url,
                   "sourceLabel": "Gods of Poker 公式", "fetchedAt": dt.date.today().isoformat(),
                   "liveAt": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%m/%d %H:%M"),
                   "lateRegNote": "公式の regClose(登録締切の時刻)と締切レベル(lateRegLevel)"},
        "events": events,
    }
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(1 for e in events if e["levels"])
    print(f"{args.out}: {len(events)} rows (structure {n})  {title}")


if __name__ == "__main__":
    main()
