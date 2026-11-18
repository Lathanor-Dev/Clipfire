"""
Analyse complète d'un live terminé et création des clips des moments forts.

Usage :
    python analyze.py logs/<fichier>.jsonl            # analyse + crée les clips
    python analyze.py logs/<fichier>.jsonl --dry-run  # affiche seulement les moments
    python analyze.py logs/<fichier>.jsonl --top 5
Le bot lance cette analyse tout seul à la fin de chaque live.
"""

import argparse
import os
import re
from datetime import datetime, timezone

import chatlog
import highlights

CLIP_BEFORE = float(os.environ.get("CLIP_BEFORE_SECONDS", 25))  # avant le pic (le chat réagit après l'action)
CLIP_AFTER = float(os.environ.get("CLIP_AFTER_SECONDS", 5))
MIN_DURATION, MAX_DURATION = 20, 60


def hms(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_duration(text: str) -> float:
    """'1h2m3s' -> secondes."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text or "")
    if not m:
        return float("inf")
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


def clip_window(moment, vod_start: float, vod_length: float = float("inf")):
    """(fin_offset, durée) en secondes de VOD pour un moment."""
    end = moment.end + CLIP_AFTER - vod_start
    start = moment.start - CLIP_BEFORE - vod_start
    duration = int(min(MAX_DURATION, max(MIN_DURATION, end - start)))
    end = int(min(end, vod_length))
    end = max(end, duration)          # le clip ne peut pas commencer avant 0
    return end, duration


def run(log_path: str, top: int, dry_run: bool) -> None:
    header, events = chatlog.load_log(log_path)
    msgs = sum(1 for e in events if e["k"] == "msg")
    print(f"[i] {msgs} messages analysés ({log_path})")
    moments = highlights.find_moments(events, top)
    if not moments:
        print("[i] Aucun moment fort détecté.")
        return

    vod_start = header.get("started_at") or events[0]["t"]
    broadcaster_id = editor_id = vod_id = None
    vod_length = float("inf")

    if not dry_run:
        import twitch_api as tw
        broadcaster_id = tw.get_broadcaster_id()
        editor_id = tw.get_self_id()
        vods = tw.get_vods(broadcaster_id)
        vod = next((v for v in vods if v.get("stream_id") == header.get("stream_id")), None)
        if vod is None and vods:
            vod = vods[0]
        if vod is None:
            print("[!] Aucun VOD trouvé : active « Stocker les diffusions passées » dans Twitch.")
            return
        vod_id = vod["id"]
        vod_length = parse_duration(vod.get("duration", ""))
        vod_start = datetime.fromisoformat(vod["created_at"].replace("Z", "+00:00")).timestamp()

    lines = []
    for rank, m in enumerate(moments, 1):
        end, duration = clip_window(m, vod_start, vod_length)
        at = hms(end - duration)
        why = ", ".join(m.reasons)
        print(f"[{rank:>2}] {at}  score {m.score:.1f}  — {why}")
        if dry_run:
            continue
        res = tw.create_clip_from_vod(broadcaster_id, editor_id, vod_id, end, duration,
                                      f"Moment fort #{rank}")
        if res:
            url, edit_url = res
            lines.append(f"**#{rank}** · {at} · score {m.score:.1f} — {why}\n▶️ {url}\n✂️ <{edit_url}>")
            print(f"     → {url}")

    if lines:
        tw.post_discord(f"🔥 **Résumé du live : {len(lines)} moments forts**\n\n" + "\n\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--top", type=int, default=highlights.TOP_N)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.log, args.top, args.dry_run)
