#!/usr/bin/env python3
"""共通形式の events.json から、いつもの MTT 一覧 xlsx を作る(シリーズ非依存)。

入力は scripts/fetch_*.py が出す JSON:
  {"series": {title, venue, currency, sourceUrl, sourceLabel, fetchedAt, lateRegNote},
   "events": [{date, start, late, eventNo, name, buyIn, buyInNote, gtd, isSatellite,
               isContinuation, isMain, officialGame, url, stack, levelMin}]}

シート構成は APT/PPS と同じ「MTT一覧 / 使い方・前提」、見出しは4行目。
円換算は「使い方・前提」B2 のレートを参照する数式。
あわせて人に送る用ページ(APPT Korea 形式、同名の .html)も毎回作る(--no-page で止める)。

    python3 scripts/build_mtt_workbook.py tmp/wpt-seoul-2026/events.json out.xlsx --rate 0.1137
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

WD = "月火水木金土日"
SHEET, GUIDE = "MTT一覧", "使い方・前提"
HEADER_ROW = 4
NAVY, GREY = "141D30", "F2F4F8"


def headers(cur: str):
    return [
        ("日付", 11), ("曜日", 6), ("開始", 7), ("レジ締切（レイト）", 20),
        ("Event #", 8), ("トーナメント名", 50), (f"Buy-in ({cur})", 14), ("円換算 (JPY)", 13),
        (f"Prize Pool / GTD ({cur})", 17), ("区分", 16), ("ゲーム種別", 20),
        ("スタック / 1レベル", 17), ("公式URL", 34), ("備考", 30),
    ]


def classify(e: dict) -> str:
    n = e["name"].lower()
    if e.get("isContinuation"):
        return "継続日（Day2以降）"
    if e.get("isSatellite"):
        return "サテライト"
    if e.get("isMain"):
        return "メインイベント"
    if "mini main" in n or "mini championship" in n:
        return "ミニメイン"
    if "high roller" in n:
        return "ハイローラー"
    return "サイド"


def game(e: dict) -> str:
    if e.get("game"):  # 出典側でゲーム種別が判定済みならそれを使う(Short Deck / Badugi 等)
        return e["game"]
    n = e["name"].lower()
    base = "Big O" if "big o" in n else "PLO" if re.search(r"omaha|plo", n) else "NLH"
    if "mystery" in n and "bounty" in n:
        return f"{base}（ミステリーバウンティ）"
    if "bounty" in n or "knockout" in n:
        return f"{base}（バウンティ）"
    return base


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("events_json")
    ap.add_argument("out_xlsx")
    ap.add_argument("--rate", type=float, required=True, help="現地通貨1単位あたりの円")
    ap.add_argument("--rate-date", default=dt.date.today().isoformat())
    ap.add_argument("--no-page", action="store_true",
                    help="人に送る用ページ(同名の .html)を作らない。既定では毎回作る")
    args = ap.parse_args()

    data = json.load(open(args.events_json, encoding="utf-8"))
    sr, evs = data["series"], data["events"]
    cur = sr.get("currency", "KRW")
    sym = {"KRW": "₩", "PHP": "₱", "TWD": "NT$", "USD": "$"}.get(cur, "")
    heads = headers(cur)

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    d0, d1 = evs[0]["date"], evs[-1]["date"]
    ws["A1"] = f"{sr['title']} MTT一覧"
    ws["A1"].font = Font(size=15, bold=True, color=NAVY)
    ws["A2"] = (f"会期 {d0.replace('-', '/')}〜{d1[5:].replace('-', '/')}｜会場 {sr['venue']}"
                f"（時刻は現地時間 KST ＝ JST）｜全 {len(evs)} 行")
    ws["A3"] = (f"出典 {sr['sourceUrl']}（{sr['sourceLabel']}・{sr['fetchedAt']} 取得）"
                f"｜円換算レート {sym}1 = {args.rate} 円（{args.rate_date}）は「{GUIDE}」B2 で変更可")
    for r in (2, 3):
        ws[f"A{r}"].font = Font(size=9, color="555555")

    thin = Side(style="thin", color="D0D5DD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for i, (h, w) in enumerate(heads, start=1):
        c = ws.cell(row=HEADER_ROW, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[HEADER_ROW].height = 30

    band = PatternFill("solid", fgColor=GREY)
    main_fill = PatternFill("solid", fgColor="FFE7EE")
    for k, e in enumerate(evs):
        i = HEADER_ROW + 1 + k
        d = dt.date.fromisoformat(e["date"])
        cat = classify(e)
        cont = e.get("isContinuation")
        stack_lv = " / ".join(x for x in [
            f"{e['stack']:,}" if e.get("stack") else "",
            f"{e['levelMin']}分" if e.get("levelMin") else ""] if x) or "—"
        late = e.get("late") or ("登録不可（継続日）" if cont else "—")
        vals = [d, WD[d.weekday()], e["start"], late, e.get("eventNo") or "—", e["name"],
                e.get("buyIn"), None, e.get("gtd"), cat, game(e), stack_lv, e["url"],
                e.get("buyInNote") or ""]
        for col, v in enumerate(vals, start=1):
            c = ws.cell(row=i, column=col, value=v)
            c.border = border
            c.font = Font(size=10, color="8A8F9C" if cont else "000000")
            if k % 2:
                c.fill = band
        ws.cell(row=i, column=1).number_format = "yyyy/mm/dd"
        if e.get("buyIn"):
            ws.cell(row=i, column=7).number_format = "#,##0"
            c8 = ws.cell(row=i, column=8, value=f"=ROUND(G{i}*'{GUIDE}'!$B$2,0)")
            c8.number_format = "#,##0"
            c8.font = Font(size=10)
        else:
            ws.cell(row=i, column=7, value="—").alignment = Alignment(horizontal="center")
        if e.get("gtd"):
            ws.cell(row=i, column=9).number_format = "#,##0"
        else:
            ws.cell(row=i, column=9, value="—").alignment = Alignment(horizontal="center")
        for col in (2, 3, 5, 12):
            ws.cell(row=i, column=col).alignment = Alignment(horizontal="center")
        u = ws.cell(row=i, column=13)
        u.hyperlink = e["url"]
        u.font = Font(size=9, color="1155CC", underline="single")
        if cat in ("メインイベント", "ミニメイン") and not cont:
            for col in range(1, 15):
                ws.cell(row=i, column=col).fill = main_fill
            ws.cell(row=i, column=6).font = Font(size=10, bold=True)

    last = HEADER_ROW + len(evs)
    ws.auto_filter.ref = f"A{HEADER_ROW}:N{last}"
    ws.freeze_panes = f"A{HEADER_ROW + 1}"
    ws.sheet_view.showGridLines = False

    g = wb.create_sheet(GUIDE)
    g.column_dimensions["A"].width = 26
    g.column_dimensions["B"].width = 96
    g["A1"] = "前提・使い方"
    g["A1"].font = Font(size=14, bold=True, color=NAVY)
    g["A2"] = f"為替レート（{sym}1 = ? 円）"
    g["B2"] = args.rate
    g["B2"].fill = PatternFill("solid", fgColor="FFF3B0")
    g["B2"].font = Font(bold=True)
    g["B2"].number_format = "0.00000"
    notes = [
        ("レートの基準日", f"{args.rate_date} 時点。B2 を書き換えると「{SHEET}」の円換算列がすべて再計算される"),
        ("時刻", "すべて現地時間の KST（UTC+9）。日本時間と同じなので時差の読み替えは不要"),
        ("出典", f"{sr['sourceLabel']}: {sr['sourceUrl']}"),
        ("Buy-in", f"参加費込みの総額（{cur}）。内訳が取れたものは「備考」列に記載"),
        ("レジ締切（レイト）", sr.get("lateRegNote", "")),
        ("区分", "メインイベント / ミニメイン / ハイローラー / サイド / サテライト / 継続日（Day2以降）。メインとミニメインはピンク、継続日は灰色の文字"),
        ("ゲーム種別", "大会名から判定（NLH / PLO / Big O、バウンティ系は括弧書き）"),
        ("スタック / 1レベル", "出典に載っているものだけ。無いシリーズは —"),
        ("注意", "主催は直前まで内容を差し替える。エントリー前に必ず公式ページで最終確認すること"),
    ]
    for n, (k2, v) in enumerate(notes, start=4):
        g.cell(row=n, column=1, value=k2).font = Font(bold=True, size=10)
        c = g.cell(row=n, column=2, value=v)
        c.font = Font(size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        g.row_dimensions[n].height = 28
    g.sheet_view.showGridLines = False

    wb.save(args.out_xlsx)
    print(f"{args.out_xlsx}: {len(evs)} rows / {d0}〜{d1}")

    # トナメリストは「xlsx ＋ 人に送る用ページ」がセット。言われなくても毎回作る
    if not args.no_page:
        from build_mtt_page import build_page
        page = str(Path(args.out_xlsx).with_suffix(".html"))
        # GitHub Pages(jny4kgr/poker-guides)にそのまま置ける単体ページで出す
        Path(page).write_text(build_page(data, args.rate, args.rate_date, standalone=True), encoding="utf-8")
        print(f"{page}: 人に送る用ページ")


if __name__ == "__main__":
    main()
