# 🔥 Clipfire

[🇬🇧 English](README.md) · 🇫🇷 Français

**Un bot qui clippe automatiquement les meilleurs moments de ton stream Twitch.**
Quand le chat s'enflamme, Clipfire crée un clip et envoie le lien dans ton salon Discord. Tu n'as plus rien à faire.

- 📈 Détecte les pics d'activité du chat (comparé à l'activité normale)
- 🎬 Crée le clip via l'API officielle Twitch
- 💬 Poste le lien dans Discord via un simple webhook (pas de bot Discord à créer)
- ⚙️ Seuils réglables, anti-spam intégré
- 🔑 Installation guidée : l'assistant récupère les tokens à ta place

---

## Installation rapide

**Prérequis :** [Python 3.10+](https://www.python.org/downloads/) et un compte Twitch.

```bash
git clone https://github.com/Lathanor-Dev/Clipfire.git
cd Clipfire

# (conseillé) environnement virtuel
python -m venv .venv
# Windows :        .venv\Scripts\activate
# Mac / Linux :    source .venv/bin/activate

pip install -r requirements.txt
python setup.py      # assistant d'installation
python bot.py        # lance le bot
```

> Sur Mac/Linux, utilise `python3` si `python` ne fonctionne pas.

Laisse `bot.py` tourner pendant ton live. C'est tout. 🎉

---

## Ce que demande l'assistant (`setup.py`)

### 1. Une app Twitch
📖 **[Guide détaillé pas à pas](docs/twitch-app-guide.fr.md)** (version rapide ci-dessous)

1. Va sur [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) → **Enregistrer votre application**.
2. **URL de redirection OAuth** : `http://localhost:3000`
3. **Catégorie** : Chat Bot · **Type de client** : Confidentiel
4. Copie le **Client ID** et génère un **Client Secret**.

### 2. Un salon Discord privé + un webhook
Tous les clips sont envoyés automatiquement dans un seul salon Discord. Mets-le en **privé** : toi seul vois les clips et tu choisis ceux qui méritent d'être publiés sur les réseaux sociaux.

1. Crée un nouveau salon et passe-le en **Salon privé** (Modifier le salon → Permissions → active *Salon privé*), puis ajoute uniquement toi (et les personnes de confiance, comme un monteur ou un modo).
2. Dans ce salon : **Modifier le salon → Intégrations → Webhooks → Nouveau webhook → Copier l'URL du webhook**.

> ⚠️ Toute personne qui a l'URL du webhook peut poster dans ton salon : garde-la secrète, comme tes tokens.

### 3. L'autorisation Twitch
L'assistant ouvre ton navigateur. Connecte-toi avec le compte qui créera les clips (le tien ou un compte bot) et clique sur **Autoriser**. Les tokens sont récupérés et enregistrés automatiquement dans `.env`, et renouvelés tout seuls ensuite.

---

## Comment ça marche

1. Clipfire lit le chat de ta chaîne (lecture anonyme, aucun accès à ton compte).
2. Il compte les messages sur une fenêtre glissante (10 s par défaut) et les compare à la moyenne des 3 dernières minutes.
3. Si l'activité dépasse le seuil (3× la moyenne et au moins 8 messages), il crée un clip.
4. Le lien est envoyé dans Discord. Un cooldown évite les clips en double.

## Publier les clips sur les réseaux sociaux

Chaque message Discord contient deux liens :

- ▶️ **Voir** : le lien normal du clip, pour vérifier si le moment est bon.
- ✂️ **Éditer / télécharger** : l'éditeur de clips Twitch, où tu peux recadrer le clip en **vertical (9:16)** pour TikTok, Reels ou Shorts et le télécharger.

Le lien d'édition donne accès à l'éditeur du clip, c'est pour ça que les clips doivent aller dans un salon **privé** (voir l'étape 2). Ne partage pas ce lien publiquement.

## Le faire tourner en permanence

Clipfire ne crée des clips que quand tu es en live, mais tu peux le laisser tourner en continu. Il se reconnecte tout seul au chat si la connexion saute et renouvelle lui-même ses tokens Twitch. Choisis ce qui te convient :

**Ton PC** (le plus simple) : lance `python bot.py` avant ton live. Sous Windows, tu peux le démarrer automatiquement avec le Planificateur de tâches.

**Un Raspberry Pi ou un petit VPS** (toujours allumé) :
1. Lance d'abord `python setup.py` sur ton ordinateur (il faut un navigateur), puis copie le fichier `.env` généré sur le serveur.
2. Ensuite, au choix :

```bash
# Option A : Docker
docker compose up -d --build
docker compose logs -f        # voir ce que fait le bot

# Option B : systemd (Linux, sans Docker)
# adapte d'abord User et les chemins dans clipfire.service
sudo cp clipfire.service /etc/systemd/system/
sudo systemctl enable --now clipfire
journalctl -u clipfire -f
```

> Ne lance **qu'une seule copie** du bot à la fois, sinon tu auras des clips en double.

## Réglages

Tout se règle dans le fichier `.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `WINDOW_SECONDS` | `10` | Durée de la fenêtre mesurée |
| `BASELINE_SECONDS` | `180` | Historique utilisé pour calculer l'activité normale |
| `SPIKE_MULTIPLIER` | `3` | Le pic doit valoir X fois la normale |
| `MIN_MESSAGES` | `8` | Nombre minimum de messages pour déclencher |
| `COOLDOWN_SECONDS` | `60` | Délai minimum entre deux clips |

**Trop de clips ?** Augmente `SPIKE_MULTIPLIER` ou `MIN_MESSAGES`.
**Pas assez ?** Baisse-les. Pour un petit chat, `MIN_MESSAGES=4` est un bon départ.

---

## Dépannage

| Problème | Solution |
|---|---|
| `Création du clip impossible : 404` | Tu n'es pas en live. Les clips ne marchent que pendant un stream. |
| `401` / token invalide | Relance `python setup.py` pour générer de nouveaux tokens. |
| Rien ne s'envoie sur Discord | Vérifie l'URL du webhook (l'assistant envoie un message de test). |
| `redirect_uri mismatch` | L'URL de redirection de ton app Twitch doit être exactement `http://localhost:3000`. |
| Le bot ne détecte rien | Baisse `MIN_MESSAGES` et `SPIKE_MULTIPLIER` dans `.env`. |

## Sécurité

Ton fichier `.env` contient tes tokens : **ne le partage jamais** et ne le publie pas (il est déjà dans le `.gitignore`).

## Contribuer

Les issues et pull requests sont les bienvenues ! Idées à développer : détection par mots-clés (`KEKW`, `POG`…), commande `!clip` manuelle, image Docker, envoi du clip dans le chat Twitch.

## Licence

[MIT](LICENSE)
