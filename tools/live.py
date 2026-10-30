#!/usr/bin/env python3
"""開催中シリーズのライブ人数を取り直す(GitHub Actions から15分ごとに実行)。

tools/series.json のうち、Gods of Poker のシリーズで会期中(from〜until。日本時間)のものだけ、
公式のシリーズページを1回取り、エントリー数・残り人数・平均スタック・進行中のレベルを
<dir>/live.json に書く。ページは開いている間 live.json を2分ごとに読み直す。
ストラクチャーや日程は毎朝の update.py の担当で、ここでは触らない。
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS / "scripts"))
from fetch_gop_series import BASE, get, live_of, series_blocks  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


def main() -> None:
    now = dt.datetime.now(JST)
    cfg = json.loads((TOOLS / "series.json").read_text(encoding="utf-8"))
    for s in cfg["series"]:
        fetch = s.get("fetch") or []
        if not fetch or fetch[0] != "fetch_gop_series.py":
            continue
        if not dt.date.fromisoformat(s["from"]) <= now.date() <= dt.date.fromisoformat(s["until"]) + dt.timedelta(days=1):
            continue
        try:
            blocks = series_blocks(get(f"{BASE}/series/{fetch[1]}"))
        except Exception as e:  # noqa: BLE001
            print(f"  取得失敗 {s['dir']}: {e}")
            continue
        # 始まっていないイベントは載せない(ページ側は「載っていない＝人数なし」として扱う)
        events = {eid: v for eid, h in blocks.items() if (v := live_of(h))}
        out = ROOT / s["dir"] / "live.json"
        old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        if old.get("events") == events:
            print(f"  変化なし {s['dir']}")
            continue
        out.write_text(json.dumps({"at": f"{now:%m/%d %H:%M}", "events": events}, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"  更新 {s['dir']}: 進行中 {sum(1 for v in events.values() if v.get('running'))} 件")


if __name__ == "__main__":
    main()
