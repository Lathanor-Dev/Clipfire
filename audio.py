"""Analyse du volume audio d'un stream/VOD avec ffmpeg (aucune bibliothèque Python en plus)."""

import re
import subprocess

_RMS = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(\S+)")
FLOOR_DB = -80.0


def loudness_per_second(path: str) -> list:
    """Niveau sonore moyen (dB) de chaque seconde du fichier audio/vidéo."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "8000",
        "-af", "aresample=8000,asetnsamples=n=8000:p=0,astats=metadata=1:reset=1,"
               "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-300:])
    levels = []
    for m in _RMS.finditer(r.stdout):
        v = m.group(1)
        levels.append(FLOOR_DB if v in ("-inf", "nan") else max(float(v), FLOOR_DB))
    return levels
