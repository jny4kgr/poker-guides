#!/usr/bin/env python3
"""共通形式の events.json から、人に送る用の1枚ページ(HTML)を作る(シリーズ非依存)。

体裁は APPT Korea ガイド(site/appt-korea-2026/index.html)をビルド時に読み込み、
合わない箇所だけ差し替える。差し替え箇所が見つからなければ落とす(テンプレート
側の変更に気づけるように)。build_mtt_workbook.py から毎回自動で呼ばれるので、
トナメリストを作ると xlsx とこのページが必ずセットで出る。

APPT Korea 版との差分:
- データは GAS の ?format=json を fetch せず HTML に埋め込む(単体で配れる)
- GAME / カードの色分けは共通形式の isSatellite・isContinuation・大会名から判定
- 通貨記号はシリーズの通貨に合わせる。BUY-IN の区切りは KRW 以外なら円換算で判定
- ブラインド額は出典に無い前提の文言にする(毎朝の同期は無いので、その旨は出さない)

    python3 scripts/build_mtt_page.py tmp/gop-incheon-2026-ii/events.json out.html --rate 0.11374
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_mtt_workbook import WD, classify, game  # noqa: E402

TEMPLATE = ROOT / "site" / "appt-korea-2026" / "index.html"
SYM = {"KRW": "₩", "PHP": "₱", "TWD": "NT$", "USD": "$", "JPY": "¥"}


def sub(doc: str, old: str, new: str) -> str:
    if old not in doc:
        sys.exit(f"テンプレートに差し替え箇所が見つからない: {old[:70]}…")
    return doc.replace(old, new)


def to_page_events(evs: list, rate: float) -> list:
    out = []
    for i, e in enumerate(evs):
        d = dt.date.fromisoformat(e["date"])
        cont = bool(e.get("isContinuation"))
        g = game(e)
        key = "SAT" if e.get("isSatellite") else ("NLHE" if g.startswith("NLH") else "OTHER")
        out.append({
            "id": str(i), "date": e["date"], "weekday": WD[d.weekday()],
            "start": e["start"], "late": "Closed" if cont else (e.get("late") or "—"),
            "eventNo": e.get("eventNo") or "", "name": e["name"],
            "category": classify(e), "game": g, "gameType": "", "gameKey": key,
            "stripe": "sat" if key == "SAT" else "cont" if cont else "other" if key == "OTHER" else "",
            "isContinuation": cont,
            "buyInKrw": e.get("buyIn"), "buyInJpy": round(e["buyIn"] * rate) if e.get("buyIn") else None,
            "prizePoolKrw": e.get("gtd"), "chips": e.get("stack"), "clock": e.get("levelMin"),
            "note": e.get("buyInNote") or "", "sourceUrl": e.get("url") or "",
        })
    return out


def build_page(data: dict, rate: float, rate_date: str, standalone: bool = False) -> str:
    """standalone=True なら <html>/<head>/<body> を残す(GitHub Pages 等にそのまま置ける)。
    False は Artifact 用(Artifact が外枠を自前で付けるので外す)。"""
    sr = data["series"]
    cur = sr.get("currency", "KRW")
    sym = SYM.get(cur, "")
    evs = to_page_events(data["events"], rate)
    d0, d1 = dt.date.fromisoformat(evs[0]["date"]), dt.date.fromisoformat(evs[-1]["date"])
    span = (f"{d0:%b} {d0.day}-{d1.day}" if d0.month == d1.month else f"{d0:%b} {d0.day} - {d1:%b} {d1.day}")
    title = sr["title"]
    payload = {"title": title, "subtitle": f"MTT Schedule | {span}", "rate": rate,
               "updatedAt": sr.get("fetchedAt", dt.date.today().isoformat()),
               "blindStatus": "", "events": evs}

    doc = TEMPLATE.read_text(encoding="utf-8")
    if not standalone:
        # Artifact は <html>/<head>/<body> を自前で付けるので外す
        doc = re.sub(r"^<!doctype html>.*?<title>", "<title>", doc, count=1, flags=re.S)
        doc = sub(doc, "</style></head><body>", "</style>")
        doc = sub(doc, "</script></body></html>", "</script>")
    doc = sub(doc, "<title>APPT Korea 2026</title>", f"<title>{title}</title>")
    doc = sub(doc, '<h1 id="title">APPT Korea 2026</h1>', f'<h1 id="title">{title}</h1>')
    doc = sub(doc, '<p class="sub" id="subtitle">MTT Schedule | Sep 3-14</p>',
              f'<p class="sub" id="subtitle">{payload["subtitle"]}</p>')
    doc = sub(doc, "<span>📍 Paradise City, Incheon</span>", f"<span>📍 {sr['venue']}</span>")
    # GAME フィルタと色分けは共通形式から判定した gameKey / stripe を使う
    doc = sub(doc, "g=state.game==='ALL'||(state.game==='NLHE'&&e.game==='NLHE'&&e.category!=='サテライト')"
                   "||(state.game==='SAT'&&e.category==='サテライト')"
                   "||(state.game==='OTHER'&&e.game!=='NLHE'&&e.category!=='サテライト')",
              "g=state.game==='ALL'||state.game===e.gameKey")
    doc = sub(doc, "const c=e.category==='サテライト'?'sat':e.isContinuation?'cont':e.game!=='NLHE'?'other':'';",
              "const c=e.stripe||'';")
    if cur != "KRW":
        # 金額の記号と BUY-IN の区切り(₩700K / ₩3M 相当を円換算で)を通貨に合わせる
        doc = doc.replace("'₩'+", f"'{sym}'+")
        doc = sub(doc, "`₩1 = ¥${d.rate}`", f"`{sym}1 = ¥${{d.rate}}`")
        doc = sub(doc, "p=e.buyInKrw||0", "p=(e.buyInJpy||0)/0.1137")
        # ボタンの表記も円に(区切りは ₩700K ≒ ¥8万、₩3M ≒ ¥34万)
        doc = sub(doc, 'data-v="LOW">〜₩700K<', 'data-v="LOW">〜¥8万<')
        doc = sub(doc, 'data-v="MID">₩700K〜₩3M<', 'data-v="MID">¥8万〜¥34万<')
        doc = sub(doc, 'data-v="HIGH">₩3M〜<', 'data-v="HIGH">¥34万〜<')
    # 毎朝の同期は無いので、その旨の文言は出さない
    doc = sub(doc, "は公式・取得元とも未公開です。毎朝の自動同期で公開をチェックしています${st?`（${esc(st)}）`:''}。",
              "は出典に載っていません。")
    doc = sub(doc, "Schedule data is loaded via Google Sheets. レベル時間は公表分のみ収録。",
              f"時刻はすべて現地時間（KST ＝ 日本時間）。円は {sym}1 = ¥{rate}（{rate_date}）換算の目安。<br>"
              f"出典: {sr['sourceLabel']}（{sr.get('fetchedAt', '')} 取得）。"
              "主催は直前まで内容を差し替えます。エントリー前に公式ページで最終確認を。")
    doc, n = re.subn(r"const DATA_URL=.*?\.catch\(fail\);",
                     lambda _: "const DATA=" + json.dumps(payload, ensure_ascii=False) + ";\nstart(DATA);",
                     doc, count=1, flags=re.S)
    if n != 1:
        sys.exit("テンプレートに fetch ブロックが見つからない")
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("events_json")
    ap.add_argument("out_html")
    ap.add_argument("--rate", type=float, required=True)
    ap.add_argument("--rate-date", default=dt.date.today().isoformat())
    ap.add_argument("--standalone", action="store_true",
                    help="<html>/<head>/<body> を残した単体ページにする(GitHub Pages 等に置く用)")
    args = ap.parse_args()
    data = json.load(open(args.events_json, encoding="utf-8"))
    Path(args.out_html).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_html).write_text(build_page(data, args.rate, args.rate_date, args.standalone),
                                   encoding="utf-8")
    print(f"{args.out_html}: {len(data['events'])} events")


if __name__ == "__main__":
    main()
