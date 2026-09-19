#!/usr/bin/env python3
"""Asian Poker Tour(theasianpokertour.com)のシリーズ日程を取得し、共通形式の JSON にする。

公式は SvelteKit 製で、/series/<slug>/events の HTML にイベントがインラインの JS オブジェクト
(`{startTimeUTC:"…",…,name:"…",buyin:"…",fee:"…",isMainEvent:…,isSatellite:…,regCloseUTC:…}`)
として入っている。時刻は UTC なので現地時間(--tz-hours、韓国なら 9)に直す。
同じイベントが複数回出てくるので documentId で重複を除く。スタックとレベル時間は無い。

    python3 scripts/fetch_apt_series.py apt-jeju-south-korea-2026 tmp/apt-jeju-2026/events.json \
        --title "APT Jeju 2026" --venue "LES A Casino（済州 神話ワールド）" --tz-hours 9
"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://www.theasianpokertour.com/series"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--venue", required=True)
    ap.add_argument("--tz-hours", type=int, required=True)
    ap.add_argument("--fx", action="append", default=[],
                    help="シリーズ通貨と違う通貨の換算(例: USD=31.835 は 1USD=31.835 シリーズ通貨)。複数可")
    args = ap.parse_args()
    fx = {k.upper(): float(v) for k, v in (x.split("=", 1) for x in args.fx)}

    url = f"{BASE}/{args.slug}/events"
    page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                  timeout=30).read().decode("utf-8", "replace")
    tz = dt.timezone(dt.timedelta(hours=args.tz_hours))
    seen, evs, cur = set(), [], "KRW"
    for b in page.split("{startTimeUTC:")[1:]:
        head = b[:3000]
        m = re.match(r'"([^"]+)"', head)
        g = lambda k: (re.search(r"\b" + k + r':"([^"]*)"', head) or [None, None])[1]  # noqa: E731
        doc, name = g("documentId"), (g("name") or "").strip()
        if not m or not doc or not name or doc in seen:
            continue
        seen.add(doc)
        st = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(tz)
        cont = bool(re.search(r"\bDay\s*[2-9]\b|Final Day|\bFinal\b(?! Table Bonus)", name, re.I))
        late = ""
        rc = g("regCloseUTC")
        if rc and not cont:
            c = dt.datetime.fromisoformat(rc.replace("Z", "+00:00")).astimezone(tz)
            # 公式データに開始より前(例: Jeju メインの 6/5)の締切が入っていることがある。範囲外は空欄
            if st <= c <= st + dt.timedelta(days=2):
                late = f"{c:%H:%M}" if c.date() == st.date() else f"{c.month}/{c.day} {c:%H:%M}"
        buy, fee = g("buyin"), g("fee")
        try:
            total = int(float(buy or 0) + float(fee or 0)) or None
        except ValueError:
            total = None
        ecur = (g("currency") or cur).upper()
        mg = re.search(r"(?:\b(KRW|TWD|USD|PHP|HKD|JPY)\s*)?([\d,]{6,})\s*GTD", name)
        pp = g("prizePool")
        gtd = int(mg.group(2).replace(",", "")) if mg else (int(float(pp)) if pp and float(pp) > 0 else None)
        gcur = (mg.group(1) or ecur) if mg else ecur
        gt = (g("gameType") or "")
        game = ("PLO" if re.search(r"omaha", gt, re.I) else
                "Mixed" if re.search(r"stud|razz|draw|mix|badugi", gt + " " + name, re.I) else "")
        no = (re.search(r"\[Event\s*(\d+)\]", name) or [None, ""])[1]
        evs.append({
            "date": f"{st:%Y-%m-%d}", "start": f"{st:%H:%M}", "late": late, "eventNo": no, "name": name,
            "buyIn": None if cont else total,
            "buyInNote": (f"{int(float(buy)):,} + {int(float(fee)):,}" if buy and fee and float(fee) > 0 and not cont else ""),
            "gtd": gtd, "_cur": ecur, "_gcur": gcur, "isSatellite": "isSatellite:true" in head, "isContinuation": cont,
            "isMain": "isMainEvent:true" in head,
            "game": game, "officialGame": gt, "url": f"{url}/{doc}", "stack": None, "levelMin": None,
        })
    # シリーズ通貨 = いちばん多い通貨。違う通貨(台北メインの USD 等)は --fx で換算し、元の額は備考に残す
    from collections import Counter
    cur = Counter(e["_cur"] for e in evs).most_common(1)[0][0] if evs else cur
    for e in evs:
        ec, gc = e.pop("_cur"), e.pop("_gcur")
        if ec != cur and e["buyIn"]:
            if ec not in fx:
                raise SystemExit(f"{ec} 建てのイベントがある。--fx {ec}=<1{ec}あたりの{cur}> を指定する")
            orig = e["buyIn"]
            e["buyIn"] = round(orig * fx[ec])
            e["buyInNote"] = f"{ec} {e['buyInNote'] or f'{orig:,}'}（{ec}1 = {cur}{fx[ec]} で換算）"
        if gc != cur and e["gtd"]:
            if gc not in fx:
                raise SystemExit(f"{gc} 建ての保証額がある。--fx {gc}=<1{gc}あたりの{cur}> を指定する")
            e["gtd"] = round(e["gtd"] * fx[gc])
    evs.sort(key=lambda e: (e["date"], e["start"], e["eventNo"]))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump({"series": {"title": args.title, "venue": args.venue, "currency": cur, "sourceUrl": url,
                          "sourceLabel": "Asian Poker Tour 公式", "fetchedAt": dt.date.today().isoformat(),
                          "lateRegNote": "公式の regCloseUTC を現地時間に直したもの"},
               "events": evs}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{args.out}: {len(evs)} rows")


if __name__ == "__main__":
    main()
