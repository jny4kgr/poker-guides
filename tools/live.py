#!/usr/bin/env python3
"""開催中シリーズのライブ人数を取り直す(GitHub Actions のループから10分ごとに実行)。

tools/series.json のうち会期中(from〜until。日本時間)のシリーズについて <dir>/live.json を書く。
- Gods of Poker: 公式のシリーズページ1回で、エントリー数・残り人数・平均スタック・進行中のレベル
- --somuchpoker 付きのシリーズ(WPT): SoMuchPoker の日程ページ1回で、終わった大会のエントリー数・賞金総額と進行中の印
ページは開いている間 live.json を2分ごとに読み直す。
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
import somuchpoker  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


def live_source(s: dict):
    f = s.get("fetch") or [""]
    if f[0] == "fetch_gop_series.py":
        return ("gop", f[1])
    if "--somuchpoker" in f:
        return ("smp", f[f.index("--somuchpoker") + 1])
    return None


def fetch_live(src) -> dict:
    kind, key = src
    if kind == "gop":
        # 始まっていないイベントは載せない(ページ側は「載っていない＝人数なし」として扱う)
        return {eid: v for eid, h in series_blocks(get(f"{BASE}/series/{key}")).items() if (v := live_of(h))}
    return somuchpoker.live_map(key)


def active(now: dt.datetime) -> list:
    """会期中(from〜until の翌日。日本時間)で、人数を取れるシリーズ"""
    cfg = json.loads((TOOLS / "series.json").read_text(encoding="utf-8"))
    return [s for s in cfg["series"] if live_source(s)
            and dt.date.fromisoformat(s["from"]) <= now.date() <= dt.date.fromisoformat(s["until"]) + dt.timedelta(days=1)]


def main() -> None:
    now = dt.datetime.now(JST)
    if sys.argv[1:] == ["--check"]:  # 会期中のシリーズがあれば終了コード 0(workflow のループ継続判定)
        sys.exit(0 if active(now) else 1)
    for s in active(now):
        try:
            events = fetch_live(live_source(s))
        except Exception as e:  # noqa: BLE001
            print(f"  取得失敗 {s['dir']}: {e}")
            continue
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
