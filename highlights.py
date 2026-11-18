"""
Détection des moments forts à partir du chat complet d'un live.

Principe : on découpe le live en fenêtres glissantes et on mesure, pour chacune,
plusieurs signaux (débit de messages, nombre de chatteurs différents, messages
« hype » comme LUL/KEKW/mdr/clip, MAJUSCULES, subs/raids/bits). Chaque signal est
comparé à la normale de CE live (médiane robuste), puis combiné en un score.
Les meilleurs pics, espacés les uns des autres, deviennent des moments forts.
Pur Python, sans réseau.
"""

import bisect
import os
import re
import statistics
from dataclasses import dataclass, field

WINDOW = float(os.environ.get("HL_WINDOW_SECONDS", 10))
STEP = float(os.environ.get("HL_STEP_SECONDS", 2))
MIN_GAP = float(os.environ.get("HL_MIN_GAP_SECONDS", 60))      # écart mini entre 2 moments
MIN_SCORE = float(os.environ.get("HL_MIN_SCORE", 4.5))
MIN_MESSAGES = int(os.environ.get("HL_MIN_MESSAGES", 6))        # plancher absolu par fenêtre
TOP_N = int(os.environ.get("HL_TOP_CLIPS", 10))
SKIP_START = float(os.environ.get("HL_SKIP_START_SECONDS", 240))  # ignore le début (spam d'ouverture)
SKIP_END = float(os.environ.get("HL_SKIP_END_SECONDS", 0))
MAX_PER_USER = int(os.environ.get("HL_MAX_MSGS_PER_USER", 2))      # anti-spam : par fenêtre
AUDIO_WEIGHT = float(os.environ.get("HL_AUDIO_WEIGHT", 1.2))

HYPE_RE = re.compile(
    r"\b(lul|lol|lmao|kekw|omegalul|pog\w*|wtf|omg|gg|ez|clip|mdr|ptdr|haha\w*|"
    r"insane|nooo+|wow|rip|oof|monkas|pepega|ouf|incroyable|malade|banger)\b"
    r"|😂|🤣|😱|🔥|💀|😭",
    re.I,
)


@dataclass
class Moment:
    start: float          # epoch (début de la zone chaude)
    end: float
    peak: float           # centre de la fenêtre la plus chaude
    score: float
    reasons: list = field(default_factory=list)


def _is_shout(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) > 0.7


def _robust_z(values: list) -> list:
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values)
    scale = max(1.4826 * mad, statistics.pstdev(values) * 0.5, 1.0)
    return [max(0.0, (v - med) / scale) for v in values]


def _clean_messages(chunk: list) -> list:
    """Retire les commandes (!join…) et limite les messages par personne (anti-spam)."""
    seen, out = {}, []
    for e in chunk:
        if e["k"] != "msg" or e["m"].startswith("!"):
            continue
        seen[e["u"]] = seen.get(e["u"], 0) + 1
        if seen[e["u"]] <= MAX_PER_USER:
            out.append(e)
    return out


def find_moments(events: list, top_n: int = TOP_N, audio=None, stream_start: float = None) -> list:
    """
    events : liste triée de {t,k,u,m,w}.
    audio  : (t0, [niveau en dB par seconde]) ou None — volume du stream, aligné sur t0 (epoch).
    stream_start : début du live (epoch) pour ignorer SKIP_START secondes d'ouverture.
    """
    if not events or (audio is None and sum(e["k"] == "msg" for e in events) < MIN_MESSAGES):
        return []
    t0, t1 = events[0]["t"], events[-1]["t"]
    if audio:
        t0, t1 = min(t0, audio[0]), max(t1, audio[0] + len(audio[1]))
    stream_start = stream_start if stream_start is not None else t0
    times = [e["t"] for e in events]

    starts, feats = [], []
    s = t0
    while s + WINDOW <= t1 + STEP:
        lo, hi = bisect.bisect_left(times, s), bisect.bisect_left(times, s + WINDOW)
        chunk = events[lo:hi]
        m = _clean_messages(chunk)
        loud = None
        if audio:
            i0 = max(0, int(s - audio[0])); i1 = int(s + WINDOW - audio[0])
            seg = audio[1][i0:i1]
            loud = sum(seg) / len(seg) if seg else None
        feats.append({
            "rate": len(m),
            "uniq": len({e["u"] for e in m}),
            "hype": sum(1 for e in m if HYPE_RE.search(e["m"])),
            "shout": sum(1 for e in m if _is_shout(e["m"])),
            "ev": sum(e.get("w", 0) for e in chunk),
            "loud": loud,
        })
        starts.append(s)
        s += STEP

    z = {k: _robust_z([f[k] for f in feats]) for k in ("rate", "uniq", "hype", "shout")}
    if audio:
        known = [f["loud"] for f in feats if f["loud"] is not None]
        med = statistics.median(known) if known else 0
        z["loud"] = _robust_z([f["loud"] if f["loud"] is not None else med for f in feats])
    else:
        z["loud"] = [0.0] * len(feats)

    def parts_of(j):
        f = feats[j]
        return {
            "rate": 1.0 * z["rate"][j],
            "uniq": 0.6 * z["uniq"][j],
            "hype": 0.8 * z["hype"][j],
            "shout": 0.3 * z["shout"][j],
            "ev": 0.3 * min(f["ev"], 10),
            "loud": AUDIO_WEIGHT * z["loud"][j],
        }

    scored = []
    for i, f in enumerate(feats):
        if starts[i] < stream_start + SKIP_START or starts[i] + WINDOW > t1 - SKIP_END:
            continue
        if f["rate"] < MIN_MESSAGES and f["ev"] < 3 and z["loud"][i] < 2:
            continue
        parts = parts_of(i)
        scored.append((sum(parts.values()), i, parts))

    scored.sort(reverse=True)
    picked, moments = [], []
    for score, i, parts in scored:
        if score < MIN_SCORE or len(moments) >= top_n:
            break
        centre = starts[i] + WINDOW / 2
        if any(abs(centre - c) < MIN_GAP for c in picked):
            continue
        picked.append(centre)
        # étend la zone chaude tant que le score reste > 50 % du pic (max ±30 s)
        lo_i = hi_i = i
        thr = score * 0.5
        while lo_i > 0 and starts[i] - starts[lo_i - 1] <= 30 and sum(parts_of(lo_i - 1).values()) >= thr:
            lo_i -= 1
        while hi_i < len(starts) - 1 and starts[hi_i + 1] - starts[i] <= 30 and sum(parts_of(hi_i + 1).values()) >= thr:
            hi_i += 1
        moments.append(Moment(
            start=starts[lo_i], end=starts[hi_i] + WINDOW, peak=centre,
            score=score, reasons=_reasons(feats[i], parts),
        ))
    return moments


def _reasons(f: dict, parts: dict) -> list:
    out = []
    if parts["loud"] > 1.5:
        out.append("le streamer crie / rit (volume audio en pic)")
    if parts["rate"] > 1:
        out.append(f"chat en feu ({f['rate']} msgs/{WINDOW:.0f}s, {f['uniq']} chatteurs)")
    if f["hype"] >= 3:
        out.append(f"{f['hype']} messages hype (LUL/KEKW/clip…)")
    if f["shout"] >= 3:
        out.append(f"{f['shout']} messages en MAJUSCULES")
    if f["ev"] >= 3:
        out.append("subs/raid/bits")
    return out or ["pic d'activité"]
