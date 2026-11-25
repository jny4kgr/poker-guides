#!/usr/bin/env python3
"""CTP Club(ctpclub.app、台北の CTP / Red Space)のフェスティバル日程を取得し、共通形式の JSON にする。

公式の /en/festivals/<slug> は SvelteKit のサーバー描画で、全日程が HTML に入っている。
タグを外すと「Wednesday, January 13, 2027」の日付見出しのあとに、1大会ずつ
Event #N / (Reg Open 等の状態) / 名前 / Buy-in: NT$X (a+b) / [Prize Pool: NT$Y] /
Time: HH:MM / Level time: Nmin / Reg. closes: LV8@21:40 の順で並ぶ。時刻は台湾時間。

    python3 scripts/fetch_ctp_festival.py taiwan-millions-tournament-21 tmp/tmt-21/events.json \
        --title "TMT 21（Taiwan Millions）" --venue "Red Space（台北）"
"""
import argparse
import datetime as dt
import html
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://ctpclub.app/en/festivals"
DAY = re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+ \d+, \d{4})$")
STATUS = {"Reg Open", "Reg Closed", "Running", "Completed", "Cancelled", "Canceled", "Upcoming", "Late Reg"}


def num(s: str):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def lines(page: str) -> list:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [x.strip() for x in t.split("\n") if x.strip() and not x.strip().startswith("p]:")]


def parse(L: list, url: str) -> list:
    evs, day, i = [], None, 0
    while i < len(L):
        m = DAY.match(L[i])
        if m:
            day = dt.datetime.strptime(m.group(2), "%B %d, %Y").date().isoformat()
        elif L[i].startswith("Event #") and day:
            no = L[i][len("Event #"):].strip()
            j = i + 1
            head = []
            while j < len(L) and L[j] != "Buy-in:":
                head.append(L[j])
                j += 1
            # 名前はタグで複数行に割れることがある(例: "MegaStack" / "GTD:NT$1,000,000")
            name = " ".join(h for h in head if h not in STATUS).strip('"“” ')
            f = {}
            k = j
            while k < len(L) and not L[k].startswith("Event #") and not DAY.match(L[k]) and not L[k].startswith("©"):
                if L[k].endswith(":") and k + 1 < len(L):
                    f[L[k][:-1]] = L[k + 1]
                    if L[k] == "Buy-in:" and k + 2 < len(L) and L[k + 2].startswith("("):
                        f["note"] = L[k + 2].strip("()")
                k += 1
            # 「LV0@」は締切がまだ載っていない印
            late = re.match(r"LV([1-9]\d*)@([\d:]+)", f.get("Reg. closes", ""))
            buy = num(f.get("Buy-in"))
            # Day 2 以降・Final は新規エントリーなし(CTP は継続日にも Day 1 のバイインを並べる)
            cont = bool(re.search(r"\bDay ?[2-9]\b|\bFinal\b", name))
            sat = bool(re.search(r"Satellite|\bSAT\b|Freeroll|Stair|MegaStack Stair", name, re.I))
            evs.append({
                "date": day, "start": f.get("Time", ""), "late": late.group(2) if late else "",
                "lateLv": int(late.group(1)) if late else None, "eventNo": no,
                "name": re.sub(r"\s+", " ", name), "buyIn": None if cont else (buy or None),
                "buyInNote": "前日までの勝ち残りのみ" if cont else f.get("note", ""),
                "gtd": num(f.get("Prize Pool")), "isSatellite": sat,
                "isContinuation": cont, "isMain": bool(re.search(r"Main Event", name, re.I)) and not sat
                and not re.search(r"Mini", name, re.I),
                "game": "", "url": url, "stack": None, "levelMin": num(f.get("Level time")),
            })
            i = k
            continue
        i += 1
    return sorted(evs, key=lambda e: (e["date"], e["start"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--venue", required=True)
    a = ap.parse_args()
    url = f"{BASE}/{a.slug}"
    page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8")
    evs = parse(lines(page), url)
    data = {"series": {"title": a.title, "venue": a.venue, "currency": "TWD", "sourceUrl": url,
                       "sourceLabel": "CTP Club 公式", "fetchedAt": dt.date.today().isoformat(),
                       "tzLabel": "台湾時間 ＝ 日本時間 −1時間"},
            "events": evs}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{a.out}: {len(evs)} rows")


if __name__ == "__main__":
    main()
