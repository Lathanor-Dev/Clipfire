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

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Configuration (voir .env) ------------------------------------------------
CHANNEL = os.environ["TWITCH_CHANNEL"].lower().lstrip("#")
CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
ACCESS_TOKEN = os.environ["TWITCH_ACCESS_TOKEN"]
REFRESH_TOKEN = os.environ.get("TWITCH_REFRESH_TOKEN", "")
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]

WINDOW_SECONDS = float(os.environ.get("WINDOW_SECONDS", 10))      # fenêtre mesurée
BASELINE_SECONDS = float(os.environ.get("BASELINE_SECONDS", 180))  # historique de référence
SPIKE_MULTIPLIER = float(os.environ.get("SPIKE_MULTIPLIER", 3))    # x la moyenne
MIN_MESSAGES = int(os.environ.get("MIN_MESSAGES", 8))              # plancher absolu
COOLDOWN_SECONDS = float(os.environ.get("COOLDOWN_SECONDS", 60))   # entre deux clips

HELIX = "https://api.twitch.tv/helix"


# --- API Twitch ---------------------------------------------------------------
def _headers():
    return {"Authorization": f"Bearer {ACCESS_TOKEN}", "Client-Id": CLIENT_ID}


def refresh_access_token() -> bool:
    """Renouvelle le token si un refresh token est fourni."""
    global ACCESS_TOKEN, REFRESH_TOKEN
    if not (REFRESH_TOKEN and CLIENT_SECRET):
        return False
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10,
    )
    if r.status_code != 200:
        print(f"[!] Échec du refresh du token : {r.status_code} {r.text}")
        return False
    data = r.json()
    ACCESS_TOKEN = data["access_token"]
    REFRESH_TOKEN = data.get("refresh_token", REFRESH_TOKEN)
    _save_tokens()
    print("[i] Token Twitch renouvelé.")
    return True


def _save_tokens() -> None:
    """Sauvegarde les tokens renouvelés dans .env pour le prochain lancement."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    updates = {"TWITCH_ACCESS_TOKEN": ACCESS_TOKEN, "TWITCH_REFRESH_TOKEN": REFRESH_TOKEN}
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def helix(method: str, path: str, **kwargs) -> requests.Response:
    r = requests.request(method, f"{HELIX}{path}", headers=_headers(), timeout=10, **kwargs)
    if r.status_code == 401 and refresh_access_token():
        r = requests.request(method, f"{HELIX}{path}", headers=_headers(), timeout=10, **kwargs)
    return r


def get_broadcaster_id() -> str:
    r = helix("GET", "/users", params={"login": CHANNEL})
    r.raise_for_status()
    return r.json()["data"][0]["id"]


def create_clip(broadcaster_id: str) -> str | None:
    """Crée un clip et renvoie son URL (ou None en cas d'échec)."""
    r = helix("POST", "/clips", params={"broadcaster_id": broadcaster_id})
    if r.status_code != 202:
        print(f"[!] Création du clip impossible : {r.status_code} {r.text}")
        return None
    clip_id = r.json()["data"][0]["id"]

    # Le clip met quelques secondes à être disponible.
    for _ in range(10):
        time.sleep(2)
        c = helix("GET", "/clips", params={"id": clip_id})
        if c.status_code == 200 and c.json().get("data"):
            return c.json()["data"][0]["url"]
    return f"https://clips.twitch.tv/{clip_id}"


def send_to_discord(url: str, count: int, baseline: float) -> None:
    content = (
        f"🎬 **Nouveau clip !** (pic de chat : {count} messages en "
        f"{WINDOW_SECONDS:.0f}s, normal ≈ {baseline:.1f})\n{url}"
    )
    r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    if r.status_code >= 300:
        print(f"[!] Erreur Discord : {r.status_code} {r.text}")


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


# --- Lecture du chat (IRC) ----------------------------------------------------
async def run_chat(detector: SpikeDetector, on_spike):
    nick = f"justinfan{random.randint(10000, 99999)}"
    while True:
        try:
            ctx = ssl.create_default_context()
            reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=ctx)
            writer.write(f"NICK {nick}\r\nJOIN #{CHANNEL}\r\n".encode())
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
                elif " PRIVMSG " in text:
                    now = time.time()
                    detector.add_message(now)
                    result = detector.check(now)
                    if result:
                        detector.last_clip = now
                        asyncio.create_task(on_spike(*result))
        except Exception as e:
            print(f"[!] Chat déconnecté ({e}), reconnexion dans 5s…")
            await asyncio.sleep(5)


async def main():
    broadcaster_id = await asyncio.to_thread(get_broadcaster_id)
    print(f"[i] Chaîne {CHANNEL} (id {broadcaster_id})")

    async def on_spike(count: int, baseline: float):
        print(f"[+] Pic détecté : {count} messages (normal ≈ {baseline:.1f}) → clip…")
        url = await asyncio.to_thread(create_clip, broadcaster_id)
        if url:
            print(f"[+] Clip : {url}")
            await asyncio.to_thread(send_to_discord, url, count, baseline)

    await run_chat(SpikeDetector(), on_spike)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt.")
