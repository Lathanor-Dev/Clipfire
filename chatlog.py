"""Lecture des lignes IRC Twitch et enregistrement du chat complet (JSONL)."""

import json
import os

# Poids "d'intensité" des évènements du live (abonnements, raids…)
EVENT_WEIGHTS = {
    "sub": 2, "resub": 2, "subgift": 2, "anongiftpaidupgrade": 1,
    "giftpaidupgrade": 1, "raid": 5, "bitsbadgetier": 1,
}


def parse_irc(line: str):
    """Renvoie (commande, tags, utilisateur, texte) ou None."""
    tags = {}
    if line.startswith("@"):
        raw, _, line = line.partition(" ")
        for kv in raw[1:].split(";"):
            k, _, v = kv.partition("=")
            tags[k] = v
    parts = line.split(" ", 3)
    if len(parts) < 2:
        return None
    prefix, cmd = parts[0], parts[1]
    rest = parts[3] if len(parts) > 3 else ""
    text = rest[1:] if rest.startswith(":") else rest
    user = prefix.lstrip(":").split("!", 1)[0]
    return cmd, tags, user, text


def to_event(line: str, now: float):
    """Transforme une ligne IRC en évènement {t,k,u,m,w} ou None."""
    parsed = parse_irc(line)
    if not parsed:
        return None
    cmd, tags, user, text = parsed
    try:
        t = int(tags["tmi-sent-ts"]) / 1000
    except (KeyError, ValueError):
        t = now
    if cmd == "PRIVMSG":
        ev = {"t": t, "k": "msg", "u": user, "m": text}
        bits = tags.get("bits")
        if bits and bits.isdigit():
            ev["w"] = min(int(bits) / 100, 10)
        return ev
    if cmd == "USERNOTICE":
        msg_id = tags.get("msg-id", "")
        w = EVENT_WEIGHTS.get(msg_id, 0)
        if msg_id == "submysterygift":
            w = min(int(tags.get("msg-param-mass-gift-count", "1") or 1), 10) * 2
        if w:
            return {"t": t, "k": "event", "u": user, "m": msg_id, "w": w}
    return None


class ChatLog:
    """Un fichier .jsonl par live : une ligne d'en-tête puis un évènement par ligne."""

    def __init__(self, path: str, stream_id: str, started_at: float):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        is_new = not os.path.exists(path)
        self.path = path
        self._f = open(path, "a", encoding="utf-8", buffering=1)
        if is_new:
            self._write({"k": "session", "stream_id": stream_id, "started_at": started_at})

    def _write(self, obj: dict) -> None:
        self._f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def add(self, event: dict) -> None:
        self._write(event)

    def close(self) -> None:
        self._f.close()


def load_log(path: str):
    """Renvoie (en-tête, évènements triés par temps)."""
    header, events = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("k") == "session":
                header = obj
            else:
                events.append(obj)
    events.sort(key=lambda e: e["t"])
    return header, events
