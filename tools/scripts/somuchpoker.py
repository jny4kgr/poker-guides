#!/usr/bin/env python3
"""SoMuchPoker(somuchpoker.com)の日程ページから、大会ごとの結果と進行状況を読む。

日程ページ(…/events-calendar/wpt/2026/wpt-seoul-2026/schedule)は Next.js の RSC データに
大会ごとのオブジェクト(`{"time":"11:30","lateRegistration":…,"result":{…"entries":"73"}}`)を
持っている。終わった大会はエントリー数・賞金総額、進行中の大会は live:true が入る。
開催中のエントリー数は文章の速報にしか無いので取らない。ブラインド額も無い。
fetch_wpt_yy.py(--somuchpoker)と tools/live.py から使う。
"""
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
SMP = "https://somuchpoker.com"


def _v(o: dict, k: str):
    v = o.get(k)
    return None if v in (None, "$undefined", "") else v


def schedule(url: str) -> list:
    """(日付, 大会) の一覧。同じ大会が2回出てくるので重複は除く"""
    t = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                               timeout=20).read().decode("utf-8", "replace").replace('\\"', '"')
    days = [(m.start(), m.group(1)) for m in re.finditer(r'\{"day":\d+,"date":"(\d{4}-\d\d-\d\d)"', t)]
    dec, seen, out = json.JSONDecoder(), set(), []
    for m in re.finditer(r'\{"time":"\d\d:\d\d","lateRegistration"', t):
        try:
            o, _ = dec.raw_decode(t, m.start())
        except ValueError:
            continue
        d = max((p for p in days if p[0] < m.start()), default=(0, None))[1]
        k = (d, o.get("time"), o.get("number"), o.get("name"), o.get("flight"))
        if d and k not in seen:
            seen.add(k)
            out.append((d, o))
    return out


def live_id(d: str, o: dict) -> str:
    return f"{d} {o.get('time')} #{_v(o, 'number') or ''}"


def live(o: dict) -> dict:
    """終わった大会はエントリー数と賞金総額、進行中は「進行中」だけ(人数は取れないので entries は None)"""
    r = _v(o, "result") or {}
    if isinstance(r, dict) and _v(r, "entries"):
        return {"entries": int(str(r["entries"]).replace(",", "")), "players": 0, "avg": 0,
                "phase": "終了", "running": False, "prize": _v(o, "totalPrizePool") or ""}
    if o.get("live") is True:
        return {"entries": None, "players": 0, "avg": 0, "phase": "進行中", "running": True}
    return {}


def live_map(url: str) -> dict:
    return {live_id(d, o): v for d, o in schedule(url) if (v := live(o))}


def attach(events: list, url: str) -> int:
    """共通形式の events に liveId / live を付ける(日付・開始時刻・Event # で照合)。照合できた件数を返す"""
    rows = schedule(url)
    hit = 0
    for e in events:
        c = [(d, o) for d, o in rows if d == e["date"] and o.get("time") == e["start"]]
        c = [x for x in c if (_v(x[1], "number") or "") == e["eventNo"]] or c
        if len(c) != 1:
            continue
        d, o = c[0]
        e["liveId"], e["live"] = live_id(d, o), live(o)
        hit += 1
    return hit
