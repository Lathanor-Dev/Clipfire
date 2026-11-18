"""Accès à l'API Twitch (Helix) et à Discord : configuration, tokens, clips."""

import os
import time

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


def create_clip(broadcaster_id: str) -> tuple[str, str] | None:
    """Crée un clip et renvoie (url, lien_d_édition), ou None en cas d'échec."""
    r = helix("POST", "/clips", params={"broadcaster_id": broadcaster_id})
    if r.status_code != 202:
        print(f"[!] Création du clip impossible : {r.status_code} {r.text}")
        return None
    created = r.json()["data"][0]
    clip_id = created["id"]
    edit_url = created.get("edit_url") or f"https://clips.twitch.tv/{clip_id}/edit"

    # Le clip met quelques secondes à être disponible.
    for _ in range(10):
        time.sleep(2)
        c = helix("GET", "/clips", params={"id": clip_id})
        if c.status_code == 200 and c.json().get("data"):
            return c.json()["data"][0]["url"], edit_url
    return f"https://clips.twitch.tv/{clip_id}", edit_url


def send_to_discord(url: str, edit_url: str, count: int, baseline: float, window: float) -> None:
    # Le lien d'édition permet de recadrer (ex. en vertical) et de télécharger le clip.
    # Il est envoyé dans le salon Discord PRIVÉ : ne le partage pas publiquement.
    content = (
        f"🎬 **Nouveau clip !** (pic de chat : {count} messages en "
        f"{window:.0f}s, normal ≈ {baseline:.1f})\n"
        f"▶️ Voir : {url}\n"
        f"✂️ Éditer / télécharger : <{edit_url}>"
    )
    r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    if r.status_code >= 300:
        print(f"[!] Erreur Discord : {r.status_code} {r.text}")


def get_self_id() -> str:
    """Id du compte propriétaire du token (l'« éditeur » des clips)."""
    r = helix("GET", "/users")
    r.raise_for_status()
    return r.json()["data"][0]["id"]


def get_stream(broadcaster_id: str):
    """Live en cours (dict) ou None si hors ligne."""
    r = helix("GET", "/streams", params={"user_id": broadcaster_id})
    r.raise_for_status()
    data = r.json().get("data") or []
    return data[0] if data else None


def get_vods(broadcaster_id: str) -> list:
    r = helix("GET", "/videos", params={"user_id": broadcaster_id, "type": "archive", "first": 20})
    r.raise_for_status()
    return r.json().get("data", [])


def _wait_clip(clip_id: str, edit_url: str):
    for _ in range(10):
        time.sleep(2)
        c = helix("GET", "/clips", params={"id": clip_id})
        if c.status_code == 200 and c.json().get("data"):
            return c.json()["data"][0]["url"], edit_url
    return f"https://clips.twitch.tv/{clip_id}", edit_url


def create_clip_from_vod(broadcaster_id: str, editor_id: str, vod_id: str,
                         end_offset: int, duration: int, title: str):
    """Clip d'un passage du VOD : finit à `end_offset` s et dure `duration` s (5-60)."""
    r = helix("POST", "/videos/clips", params={
        "broadcaster_id": broadcaster_id, "editor_id": editor_id, "vod_id": vod_id,
        "vod_offset": end_offset, "duration": duration, "title": title[:100],
    })
    if r.status_code not in (200, 202):
        print(f"[!] Clip VOD impossible : {r.status_code} {r.text}")
        return None
    created = r.json()["data"][0]
    edit_url = created.get("edit_url") or f"https://clips.twitch.tv/{created['id']}/edit"
    return _wait_clip(created["id"], edit_url)


def post_discord(content: str) -> None:
    r = requests.post(DISCORD_WEBHOOK, json={"content": content[:2000]}, timeout=10)
    if r.status_code >= 300:
        print(f"[!] Erreur Discord : {r.status_code} {r.text}")
