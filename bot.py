"""
Bot Twitch : crée un clip automatiquement lors d'un pic d'activité dans le chat
et envoie le lien dans un salon Discord (via webhook).

Lecture du chat : IRC anonyme (aucun token nécessaire pour lire).
Création du clip : API Helix (token utilisateur avec le scope clips:edit).
"""

import asyncio
import os
import random
import ssl
import time
from collections import deque
from datetime import datetime

import analyze
import chatlog
from twitch_api import CHANNEL, create_clip, get_broadcaster_id, get_stream, send_to_discord

# Mode « live » : clip immédiat lors d'un pic. Mode « analyse » : on enregistre tout le chat
# et, à la fin du live, on cherche les meilleurs moments pour les clipper depuis le VOD.
LIVE_CLIPS = os.environ.get("LIVE_CLIPS", "1") != "0"
AUTO_ANALYZE = os.environ.get("AUTO_ANALYZE", "1") != "0"
LOG_DIR = os.environ.get("LOG_DIR", "logs")

WINDOW_SECONDS = float(os.environ.get("WINDOW_SECONDS", 10))      # fenêtre mesurée
BASELINE_SECONDS = float(os.environ.get("BASELINE_SECONDS", 180))  # historique de référence
SPIKE_MULTIPLIER = float(os.environ.get("SPIKE_MULTIPLIER", 3))    # x la moyenne
MIN_MESSAGES = int(os.environ.get("MIN_MESSAGES", 8))              # plancher absolu
COOLDOWN_SECONDS = float(os.environ.get("COOLDOWN_SECONDS", 60))   # entre deux clips


# --- Détection de pic ---------------------------------------------------------
class SpikeDetector:
    def __init__(self):
        self.timestamps: deque[float] = deque()
        self.last_clip = 0.0

    def add_message(self, now: float) -> None:
        self.timestamps.append(now)
        while self.timestamps and now - self.timestamps[0] > BASELINE_SECONDS + WINDOW_SECONDS:
            self.timestamps.popleft()

    def check(self, now: float):
        """Renvoie (count, baseline) si un pic est détecté, sinon None."""
        if now - self.last_clip < COOLDOWN_SECONDS:
            return None
        window_start = now - WINDOW_SECONDS
        count = sum(1 for t in self.timestamps if t >= window_start)
        older = sum(1 for t in self.timestamps if t < window_start)
        # Moyenne de messages par fenêtre sur l'historique (hors fenêtre courante)
        baseline = older / (BASELINE_SECONDS / WINDOW_SECONDS)
        threshold = max(MIN_MESSAGES, SPIKE_MULTIPLIER * baseline)
        if count >= threshold:
            return count, baseline
        return None


# --- Session de live (un fichier de log par live) ----------------------------
class Session:
    def __init__(self):
        self.stream_id = None
        self.log = None

    def start(self, stream: dict) -> None:
        started = datetime.fromisoformat(stream["started_at"].replace("Z", "+00:00")).timestamp()
        path = os.path.join(LOG_DIR, f"{CHANNEL}_{stream['id']}.jsonl")
        self.stream_id = stream["id"]
        self.log = chatlog.ChatLog(path, stream["id"], started)
        print(f"[i] Live détecté, enregistrement du chat → {path}")

    def end(self) -> str:
        path = self.log.path
        self.log.close()
        self.stream_id = self.log = None
        return path

    def record(self, event: dict) -> None:
        if self.log:
            self.log.add(event)


async def watch_stream(session: Session, broadcaster_id: str):
    """Surveille le live (en ligne / hors ligne) et lance l'analyse à la fin."""
    offline_polls = 0
    while True:
        try:
            stream = await asyncio.to_thread(get_stream, broadcaster_id)
            if stream:
                offline_polls = 0
                if session.stream_id != stream["id"]:
                    session.start(stream)
            elif session.stream_id:
                offline_polls += 1
                if offline_polls >= 3:  # ~3 min hors ligne = live terminé
                    path = session.end()
                    print("[i] Live terminé.")
                    if AUTO_ANALYZE:
                        asyncio.create_task(asyncio.to_thread(_analyze_safe, path))
        except Exception as e:
            print(f"[!] Suivi du live : {e}")
        await asyncio.sleep(60)


def _analyze_safe(path: str) -> None:
    try:
        # Le VOD met un peu de temps à être prêt après la fin du live.
        time.sleep(60)
        analyze.run(path, analyze.highlights.TOP_N, dry_run=False)
    except Exception as e:
        print(f"[!] Analyse échouée ({e}). Relance : python analyze.py {path}")


# --- Lecture du chat (IRC) ----------------------------------------------------
async def run_chat(detector: SpikeDetector, on_spike, session: Session):
    nick = f"justinfan{random.randint(10000, 99999)}"
    while True:
        try:
            ctx = ssl.create_default_context()
            reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=ctx)
            writer.write(
                f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\nNICK {nick}\r\nJOIN #{CHANNEL}\r\n".encode()
            )
            await writer.drain()
            print(f"[i] Connecté au chat de #{CHANNEL}")

            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=360)
                if not line:
                    raise ConnectionError("connexion fermée")
                text = line.decode(errors="ignore").strip()
                if text.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                    continue
                now = time.time()
                event = chatlog.to_event(text, now)
                if event:
                    session.record(event)
                if " PRIVMSG " in text:
                    detector.add_message(now)
                    result = detector.check(now) if LIVE_CLIPS else None
                    if result:
                        detector.last_clip = now
                        asyncio.create_task(on_spike(*result))
        except Exception as e:
            print(f"[!] Chat déconnecté ({e}), reconnexion dans 5s…")
            await asyncio.sleep(5)


async def main():
    broadcaster_id = await asyncio.to_thread(get_broadcaster_id)
    print(f"[i] Chaîne {CHANNEL} (id {broadcaster_id})")
    print(f"[i] Clips en direct : {'oui' if LIVE_CLIPS else 'non'} · analyse de fin de live : {'oui' if AUTO_ANALYZE else 'non'}")

    session = Session()
    # Détecte un live déjà en cours AVANT de lire le chat, pour ne rien perdre.
    try:
        stream = await asyncio.to_thread(get_stream, broadcaster_id)
        if stream:
            session.start(stream)
    except Exception as e:
        print(f"[!] Impossible de lire l'état du live : {e}")

    async def on_spike(count: int, baseline: float):
        print(f"[+] Pic détecté : {count} messages (normal ≈ {baseline:.1f}) → clip…")
        result = await asyncio.to_thread(create_clip, broadcaster_id)
        if result:
            url, edit_url = result
            print(f"[+] Clip : {url}")
            await asyncio.to_thread(send_to_discord, url, edit_url, count, baseline, WINDOW_SECONDS)

    await asyncio.gather(
        run_chat(SpikeDetector(), on_spike, session),
        watch_stream(session, broadcaster_id),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt.")
