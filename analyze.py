"""
Analyse complète d'un live terminé et création des clips des moments forts.

Usage :
    python analyze.py logs/<fichier>.jsonl            # analyse + crée les clips
    python analyze.py logs/<fichier>.jsonl --dry-run  # affiche seulement les moments
    python analyze.py logs/<fichier>.jsonl --top 5
    python analyze.py logs/<fichier>.jsonl --local            # télécharge les passages (yt-dlp) et coupe en MP4
    python analyze.py logs/<fichier>.jsonl --video vod.mp4    # coupe dans un VOD déjà téléchargé (ffmpeg)
    (--local et --video analysent aussi le volume audio ; --audio le force avec les clips Twitch)
Le bot lance cette analyse tout seul à la fin de chaque live.
"""

import argparse
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

import audio as audio_mod
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


def cut_local(video: str, start: float, duration: int, out: str) -> bool:
    """Coupe [start, start+durée] d'un fichier vidéo local avec ffmpeg (précis à l'image)."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", video, "-t", str(duration),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", out],
        capture_output=True, text=True)
    if r.returncode:
        print(f"[!] ffmpeg : {r.stderr.strip()[-300:]}")
    return r.returncode == 0


def download_section(vod_id: str, start: float, duration: int, out: str) -> bool:
    """Télécharge seulement ce passage du VOD (pas tout le stream) avec yt-dlp."""
    r = subprocess.run(
        ["yt-dlp", "-q", "--no-warnings", "--download-sections", f"*{int(start)}-{int(start) + duration}",
         "--force-keyframes-at-cuts", "-o", out, f"https://www.twitch.tv/videos/{vod_id}"],
        capture_output=True, text=True)
    if r.returncode:
        print(f"[!] yt-dlp : {r.stderr.strip()[-300:]}")
    return r.returncode == 0


def fetch_audio(vod_id: str, out_dir: str) -> str:
    """Télécharge seulement la piste audio du VOD (léger) avec yt-dlp. Renvoie le chemin ou ''."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"vod_{vod_id}_audio.m4a")
    if os.path.exists(path):
        return path
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", "audio_only/worstaudio",
                        "-o", path, f"https://www.twitch.tv/videos/{vod_id}"], capture_output=True, text=True)
    if r.returncode:
        print(f"[!] yt-dlp (audio) : {r.stderr.strip()[-300:]}")
        return ""
    return path


def run(log_path: str, top: int, dry_run: bool, local: bool = False, video: str = "",
        out_dir: str = "clips", use_audio: bool = False) -> None:
    local = local or bool(video)
    use_audio = use_audio or local
    header, events = chatlog.load_log(log_path)
    msgs = sum(1 for e in events if e["k"] == "msg")
    print(f"[i] {msgs} messages analysés ({log_path})")
    vod_start = header.get("started_at") or events[0]["t"]
    broadcaster_id = editor_id = vod_id = None
    vod_length = float("inf")

    if local and not dry_run:
        for tool in (["ffmpeg"] if video else ["ffmpeg", "yt-dlp"]):
            if not shutil.which(tool):
                print(f"[!] {tool} est introuvable : installe-le (voir README).")
                return
        os.makedirs(out_dir, exist_ok=True)

    if not dry_run and not video:
        import twitch_api as tw
        broadcaster_id = tw.get_broadcaster_id()
        editor_id = None if local else tw.get_self_id()
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

    audio = None
    if use_audio:
        src = video or (fetch_audio(vod_id, out_dir) if vod_id else "")
        if src and shutil.which("ffmpeg"):
            try:
                print("[i] Analyse du volume audio…")
                audio = (vod_start, audio_mod.loudness_per_second(src))
            except Exception as e:
                print(f"[!] Audio ignoré ({e})")
        else:
            print("[i] Audio non analysé (ffmpeg absent, ou dry-run sans --video).")

    moments = highlights.find_moments(events, top, audio=audio, stream_start=header.get("started_at"))
    if not moments:
        print("[i] Aucun moment fort détecté.")
        return

    lines = []
    for rank, m in enumerate(moments, 1):
        end, duration = clip_window(m, vod_start, vod_length)
        at = hms(end - duration)
        why = ", ".join(m.reasons)
        print(f"[{rank:>2}] {at}  score {m.score:.1f}  — {why}")
        if dry_run:
            continue
        if local:
            name = os.path.join(out_dir, f"{os.path.splitext(os.path.basename(log_path))[0]}_{rank:02d}.mp4")
            start = end - duration
            ok = cut_local(video, start, duration, name) if video else download_section(vod_id, start, duration, name)
            if ok:
                lines.append(f"**#{rank}** · {at} · score {m.score:.1f} — {why}\n💾 `{name}`")
                print(f"     → {name}")
            continue
        res = tw.create_clip_from_vod(broadcaster_id, editor_id, vod_id, end, duration,
                                      f"Moment fort #{rank}")
        if res:
            url, edit_url = res
            lines.append(f"**#{rank}** · {at} · score {m.score:.1f} — {why}\n▶️ {url}\n✂️ <{edit_url}>")
            print(f"     → {url}")

    if lines and video:
        pass  # pas d'accès Twitch/Discord requis pour une coupe 100 % locale
    elif lines:
        import twitch_api as tw
        tw.post_discord(f"🔥 **Résumé du live : {len(lines)} moments forts**\n\n" + "\n\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--top", type=int, default=highlights.TOP_N)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true", help="télécharge les passages avec yt-dlp et coupe des MP4")
    ap.add_argument("--video", default="", help="VOD déjà téléchargé à découper avec ffmpeg")
    ap.add_argument("--audio", action="store_true", help="analyse aussi le volume audio (auto avec --local/--video)")
    ap.add_argument("--out", default="clips", help="dossier de sortie des MP4")
    args = ap.parse_args()
    run(args.log, args.top, args.dry_run, args.local, args.video, args.out, args.audio)
