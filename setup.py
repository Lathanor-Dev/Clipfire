"""
Assistant d'installation de Clipfire.

Il pose quelques questions, ouvre ton navigateur pour autoriser le bot sur Twitch,
récupère les tokens tout seul et écrit le fichier .env.

Lancement :  python setup.py
"""

import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import dotenv_values

PORT = 3000
REDIRECT_URI = f"http://localhost:{PORT}"
SCOPE = "clips:edit"
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def ask(label: str, default: str = "", secret: bool = False) -> str:
    hint = f" [{default}]" if default and not secret else (" [déjà rempli, Entrée pour garder]" if default else "")
    while True:
        value = input(f"{label}{hint} : ").strip()
        if value:
            return value
        if default:
            return default
        print("  → Ce champ est obligatoire.")


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        if "code" in params or "error" in params:
            type(self).result = params
            body = "<h2>Clipfire est autorisé ✅</h2><p>Tu peux fermer cet onglet et revenir au terminal.</p>"
        else:
            body = ""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


def authorize(client_id: str, client_secret: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(16)
    url = "https://id.twitch.tv/oauth2/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
        }
    )
    print("\nOuverture du navigateur pour autoriser Clipfire sur Twitch…")
    print("Si rien ne s'ouvre, copie ce lien dans ton navigateur :\n")
    print(url + "\n")
    webbrowser.open(url)

    server = HTTPServer(("localhost", PORT), _CallbackHandler)
    while not _CallbackHandler.result:
        server.handle_request()
    server.server_close()

    params = _CallbackHandler.result
    if "error" in params:
        sys.exit(f"Autorisation refusée : {params.get('error_description', params['error'])}")
    if params.get("state") != state:
        sys.exit("Erreur de sécurité (state invalide). Relance l'assistant.")

    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": params["code"],
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10,
    )
    if r.status_code != 200:
        sys.exit(f"Impossible d'obtenir le token : {r.status_code} {r.text}")
    data = r.json()
    return data["access_token"], data["refresh_token"]


def test_discord(webhook: str) -> None:
    try:
        r = requests.post(webhook, json={"content": "✅ Clipfire est bien connecté à ce salon !"}, timeout=10)
        if r.status_code < 300:
            print("  → Message de test envoyé sur Discord.")
        else:
            print(f"  ⚠ Discord a répondu {r.status_code}. Vérifie l'URL du webhook.")
    except requests.RequestException as e:
        print(f"  ⚠ Impossible de joindre Discord : {e}")


def main() -> None:
    print("=== Installation de Clipfire ===\n")
    old = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    print("1/3  Twitch")
    channel = ask("Nom de ta chaîne Twitch (sans #)", old.get("TWITCH_CHANNEL", "")).lstrip("#").lower()
    print("\n  Crée une app sur https://dev.twitch.tv/console/apps avec :")
    print(f"    - URL de redirection OAuth : {REDIRECT_URI}")
    print("    - Catégorie : Chat Bot   - Type de client : Confidentiel\n")
    client_id = ask("Client ID", old.get("TWITCH_CLIENT_ID", ""))
    client_secret = ask("Client Secret", old.get("TWITCH_CLIENT_SECRET", ""), secret=True)

    print("\n2/3  Discord")
    print("  Salon → Modifier → Intégrations → Webhooks → Nouveau webhook → Copier l'URL")
    webhook = ask("URL du webhook Discord", old.get("DISCORD_WEBHOOK_URL", ""), secret=True)
    test_discord(webhook)

    print("\n3/3  Autorisation Twitch")
    print("  Connecte-toi avec le compte qui créera les clips (ton compte ou un compte bot).")
    access, refresh = authorize(client_id, client_secret)

    settings = {
        "WINDOW_SECONDS": old.get("WINDOW_SECONDS", "10"),
        "BASELINE_SECONDS": old.get("BASELINE_SECONDS", "180"),
        "SPIKE_MULTIPLIER": old.get("SPIKE_MULTIPLIER", "3"),
        "MIN_MESSAGES": old.get("MIN_MESSAGES", "8"),
        "COOLDOWN_SECONDS": old.get("COOLDOWN_SECONDS", "60"),
    }
    lines = [
        f"TWITCH_CHANNEL={channel}",
        f"TWITCH_CLIENT_ID={client_id}",
        f"TWITCH_CLIENT_SECRET={client_secret}",
        f"TWITCH_ACCESS_TOKEN={access}",
        f"TWITCH_REFRESH_TOKEN={refresh}",
        f"DISCORD_WEBHOOK_URL={webhook}",
        "",
        "# Réglages de détection",
        *[f"{k}={v}" for k, v in settings.items()],
    ]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n✅ Terminé ! Le fichier .env a été créé.")
    print("Lance le bot avec :  python bot.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInstallation annulée.")
