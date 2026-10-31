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
            # 公式ストラクチャーとライブ人数(GOP のみ。無いシリーズは従来どおり分数からの目安表)
            "levels": e.get("levels"), "lateLv": e.get("lateLv"),
            "liveId": e.get("liveId"), "live": e.get("live") or None,
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
    payload["liveAt"] = sr.get("liveAt", "")
    doc = add_structure_and_live(doc)
    doc, n = re.subn(r"const DATA_URL=.*?\.catch\(fail\);",
                     lambda _: "const DATA=" + json.dumps(payload, ensure_ascii=False) + ";\nstart(DATA);" + LIVE_POLL + DEEPLINK_JS,
                     doc, count=1, flags=re.S)
    if n != 1:
        sys.exit("テンプレートに fetch ブロックが見つからない")
    return doc


LIVE_CSS = (".live{margin-top:10px;display:flex;flex-wrap:wrap;gap:3px 10px;align-items:baseline;font-size:12px;"
            "background:#f1f2f4;border-radius:10px;padding:7px 10px;color:var(--muted)}"
            ".live b{color:var(--ink);font-size:12px}.live.on{background:#e8f6ee;color:#14532d}.live.on b{color:#14532d}"
            ".sheet .live{margin:0 0 16px;font-size:13px}.live a{margin-left:auto;color:#1a5fb4;font-weight:800}"
            ".lv-table tr.brk td{background:#f6f6f6;color:var(--muted);font-size:12px}"
            ".lv-table td.b{font-variant-numeric:tabular-nums;font-weight:800}"
            ".lv-table td.t{white-space:nowrap}@media(max-width:480px){.lv-table{font-size:12.5px}.lv-table td{padding:7px 4px}}")

# 公式ストラクチャーがあるイベントは、分数からの目安ではなく公式のレベル表(ブラインド・休憩)を出す
STRUCT_JS = r"""
function liveLine(e,inSheet){const L=e.live;if(!L||(!L.entries&&!L.running))return '';
  const st=L.running?(L.paused?'⏸ 一時停止中':'● '+(L.phase||'進行中')):(L.phase||'');
  const n=L.entries?(!L.running&&e.isContinuation?`Day1 合計 ${fmt.format(L.entries)} entries`:`${fmt.format(L.entries)} entries`)+(L.players?` · 残り ${fmt.format(L.players)}人`:''):'エントリーなし';
  return `<div class="live ${L.running?'on':''}"><b>${esc(st)}${L.running&&L.lv?` · Lv ${L.lv}`:''}</b><span>${n}${L.running&&L.avg?` · 平均 ${fmt.format(L.avg)}`:''}</span>${inSheet&&state.liveAt?`<span>${esc(state.liveAt)} 時点</span>`:''}</div>`}
function drawLevels(e,mins){if(!e.levels||!e.levels.length)return drawLevelsEst(e,mins);
  const box=document.getElementById('lvbox'),hd=box.parentNode.querySelector('.lv-head');
  if(hd)hd.innerHTML='<strong>ストラクチャー（公式）</strong><span class="lv-empty" style="font-size:11px">BLINDS = SB / BB（ANTE）</span>';
  const s=toMin(e.start),cr=toMin(e.late),L=e.live&&e.live.running?e.live:null,now=L?null:nowMin(e.date);
  let prev=null,off=0;const close=cr==null||s==null?null:(cr<s?cr+1440:cr);
  const rows=e.levels.map(([i,sb,bb,an,m,st])=>{let a=toMin(st);if(prev!=null&&a+off<prev)off+=1440;a+=off;prev=a;const b=a+m;
    const reg=close!=null?(close>a&&close<=b):(e.lateLv&&i===e.lateLv),isNow=L?(i&&i===L.lv):(now!=null&&now>=a&&now<b);
    const tags=`${reg?'<span class="tag reg">レジ締切</span>':''}${isNow?'<span class="tag now">NOW</span>':''}`;
    if(!i)return `<tr class="brk${isNow?' now':''}"><td class="n">BREAK</td><td class="t">${hhmm(a)} – ${hhmm(b)}</td><td>${m}分 ${tags}</td></tr>`;
    return `<tr class="${reg?'reg':''}${isNow?' now':''}"><td class="n">Lv ${i}</td><td class="t">${hhmm(a)} – ${hhmm(b)}</td><td class="b">${fmt.format(sb)} / ${fmt.format(bb)}${an?` <small>(${fmt.format(an)})</small>`:''} ${tags}</td></tr>`});
  box.innerHTML=`<table class="lv-table"><tr><th>LEVEL</th><th>TIME</th><th>BLINDS</th></tr>${rows.join('')}</table>
    <p class="lv-empty" style="margin:10px 0 4px">${e.isContinuation?'継続日のストラクチャーです。':`レジ締切 ${esc(e.late)}${e.lateLv?`（Lv ${e.lateLv} 終了後の休憩まで）`:''}。`}時刻は公式の予定で、進行が押すと後ろにずれます。</p>`}
"""

LIVE_POLL = r"""
/* 開催中は live.json(15分ごとに Actions が更新)を読み直して人数を差し替える */
function applyLive(j){if(!j||!j.events)return;state.events.forEach(e=>{if(e.liveId)e.live=j.events[e.liveId]||null});
  state.liveAt=j.at||state.liveAt;updated.textContent=`Updated ${DATA.updatedAt} · 人数 ${state.liveAt} 時点`;render();
  if(state.open){const b=sheetBody.scrollTop;openSheet(state.open.id);sheetBody.scrollTop=b}}
function pollLive(){fetch('./live.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(applyLive).catch(()=>{})}
state.liveAt=DATA.liveAt||'';if(DATA.events.some(e=>e.liveId)){pollLive();setInterval(pollLive,120000)}"""


DEEPLINK_JS = r"""
/* 大会ごとのリンク: …/#27-1c で該当大会の詳細シートを開く(番号+フライト。番号なしは sat-MMDD-HHMM) */
function evBase(e){if(!e.eventNo)return `sat-${e.date.slice(5).replace('-','')}-${String(e.start||'').replace(':','')}`;
  const n=String(e.name||''),f=/Final/i.test(n)?'final':(/(?:Day|Flight)\s*(\w+)/i.exec(n)||[])[1];return f?`${e.eventNo}-${String(f).toLowerCase()}`:String(e.eventNo)}
let evKeys=null;function evKey(e){if(!evKeys){evKeys=new Map;const seen={};
  state.events.forEach(x=>{const b=evBase(x);seen[b]=(seen[b]||0)+1;evKeys.set(x,seen[b]>1?`${b}-${seen[b]}`:b)})}return evKeys.get(e)}
function openFromHash(){const h=decodeURIComponent(location.hash.slice(1)).toLowerCase();if(!h)return;
  const e=state.events.find(x=>evKey(x)===h);if(!e)return;
  if(state.date!=='ALL'&&state.date!==e.date){state.date=e.date;dateTabs();render()}
  const c=app.querySelector(`.event[data-id="${CSS.escape(String(e.id))}"]`);if(c)c.scrollIntoView({block:'center'});openSheet(e.id)}
{const o=openSheet,c=closeSheet;
  openSheet=function(id){o(id);const e=state.open;if(e)history.replaceState(null,'','#'+evKey(e))};
  closeSheet=function(){c();if(location.hash)history.replaceState(null,'',location.pathname+location.search)}}
addEventListener('hashchange',openFromHash);openFromHash();"""


def add_structure_and_live(doc: str) -> str:
    doc = sub(doc, "</style>", LIVE_CSS + "</style>")
    doc = sub(doc, "function drawLevels(e,mins){", STRUCT_JS + "function drawLevelsEst(e,mins){")
    doc = sub(doc, '<div class="more">タップで詳細・レベル対応表 ▸</div></article>',
              "${liveLine(e)}<div class=\"more\">${e.levels?'タップで詳細・ストラクチャー ▸':'タップで詳細・レベル対応表 ▸'}</div></article>")
    doc = sub(doc, '<div class="lv"><div class="lv-head">', '${liveLine(e,true)}<div class="lv"><div class="lv-head">')
    doc = sub(doc, ">公式スケジュールで確認 ▸</a>",
              ">${e.liveId?'GOP 公式でライブ状況を見る ▸':'公式スケジュールで確認 ▸'}</a>")
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
