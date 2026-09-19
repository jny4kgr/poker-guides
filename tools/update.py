#!/usr/bin/env python3
"""毎朝の自動更新(GitHub Actions から実行)。

tools/series.json のうち、終了日(until)を過ぎていないシリーズを公式から取り直し、
<dir>/index.html を作り直す。トップの index.html も series.json から毎回作り直すので、
終わったシリーズは自動で PAST に移る。1シリーズの取得に失敗しても他は続け、
失敗したシリーズは前回のページをそのまま残す。

スクリプト本体(tools/scripts/*.py)の正本は jny4kgr/it-consultant の scripts/。
あちらを直したらここへコピーする。
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS / "scripts"))
from build_mtt_page import build_page  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


def fetch_json(url: str) -> dict:
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                             timeout=20).read())


def rates(currency: str):
    """1 currency あたりの円と、その他の通貨の換算表(1X あたりの currency)。取れなければ None"""
    try:
        r = fetch_json(f"https://open.er-api.com/v6/latest/{currency}")["rates"]
        return r["JPY"], {k: 1 / v for k, v in r.items() if v}
    except Exception as e:  # noqa: BLE001
        print(f"  レート取得失敗({currency}): {e}")
        return None, {}


def update_series(s: dict, today: str) -> bool:
    jpy, cross = rates(s["currency"])
    rate = round(jpy, 5) if jpy else s["rate"]
    fx_args = []
    for cur, fallback in (s.get("fx") or {}).items():
        v = cross.get(cur.upper()) or fallback
        fx_args += ["--fx", f"{cur}={round(v, 4)}"]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "events.json"
        cmd = [sys.executable, str(TOOLS / "scripts" / s["fetch"][0]), *s["fetch"][1:2], str(out), *s["fetch"][2:], *fx_args]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            print(f"  取得失敗 {s['dir']}: {p.stderr.strip()[-300:]}")
            return False
        data = json.loads(out.read_text(encoding="utf-8"))
    if not data.get("events"):
        print(f"  イベント0件のため更新しない {s['dir']}")
        return False
    page = build_page(data, rate, today, standalone=True)
    dest = ROOT / s["dir"] / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    s["rate"] = rate
    print(f"  更新 {s['dir']}: {len(data['events'])} 件 / レート {rate}")
    return True


def card(s: dict, past: bool) -> str:
    f, u = dt.date.fromisoformat(s["from"]), dt.date.fromisoformat(s["until"])
    span = f"{f.year}/{f.month}/{f.day}〜{u.month}/{u.day}"
    cls = "card past" if past else "card"
    return f'<a class="{cls}" href="./{s["dir"]}/"><b>{s["title"]}</b><span>{span} · {s["venue"]}</span></a>'


def write_index(series: list, today: dt.date, checked: str) -> None:
    upcoming = sorted([s for s in series if dt.date.fromisoformat(s["until"]) >= today], key=lambda s: s["from"])
    past = sorted([s for s in series if dt.date.fromisoformat(s["until"]) < today], key=lambda s: s["from"], reverse=True)
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    import re
    main = ("<main>\n<h2>UPCOMING</h2>\n" + "\n".join(card(s, False) for s in upcoming) +
            "\n<h2>PAST</h2>\n" + "\n".join(card(s, True) for s in past) +
            f'\n<p class="checked">開催前・開催中のシリーズは毎朝 6:00（日本時間）に公式の日程を確認して更新しています。最終確認 {checked}</p>\n</main>')
    idx = re.sub(r"<main>.*?</main>", lambda _: main, idx, count=1, flags=re.S)
    if ".checked{" not in idx:
        idx = idx.replace("</style>", ".checked{color:var(--muted);font-size:12px;margin:14px 2px 0}</style>", 1)
    (ROOT / "index.html").write_text(idx, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(JST)
    today = now.date()
    cfg_path = TOOLS / "series.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    for s in cfg["series"]:
        if s.get("fetch") and dt.date.fromisoformat(s["until"]) >= today:
            print(f"- {s['dir']}")
            update_series(s, today.isoformat())
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_index(cfg["series"], today, f"{now:%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()
