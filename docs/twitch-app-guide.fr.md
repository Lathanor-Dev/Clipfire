# Créer ton app Twitch (pas à pas)

[🇬🇧 English](twitch-app-guide.md) · 🇫🇷 Français

Clipfire a besoin d'une petite « application » enregistrée sur Twitch. C'est gratuit, ça prend environ 2 minutes et ça te donne deux valeurs : un **Client ID** et un **Client Secret**. L'assistant d'installation (`python setup.py`) te les demandera.

> La console développeur de Twitch peut évoluer. Les noms ci-dessous sont ceux utilisés au moment de l'écriture.

---

## Avant de commencer

- Il te faut un **compte Twitch** (celui avec lequel tu streames, ou n'importe quel compte).
- Twitch exige l'**authentification à deux facteurs (2FA)** sur ton compte pour enregistrer une app. Si elle n'est pas encore activée : Twitch → Paramètres → Sécurité et confidentialité → *Configuration de l'authentification à deux facteurs*.

## Étape 1 : Ouvrir la console développeur

1. Va sur **https://dev.twitch.tv/console/apps**
2. Connecte-toi avec ton compte Twitch. Si c'est la première fois, accepte les conditions développeur.

## Étape 2 : Enregistrer l'application

Clique sur **Enregistrer votre application** (*Register Your Application*) et remplis le formulaire :

| Champ | Quoi mettre |
|---|---|
| **Nom** | Un nom unique, par exemple `Clipfire-tonpseudo`. Il doit être unique sur Twitch et ne peut pas contenir le mot « Twitch ». |
| **URL de redirection OAuth** | `http://localhost:3000` puis clique sur **Ajouter**. Ça doit être exactement ça, sans `/` à la fin. |
| **Catégorie** | `Chat Bot` |
| **Type de client** | `Confidentiel` (*Confidential*) |

Clique ensuite sur **Créer** (un captcha peut apparaître).

## Étape 3 : Récupérer le Client ID et le Client Secret

1. Ton app apparaît maintenant dans la liste. Clique sur **Gérer** (*Manage*).
2. Copie le **Client ID** (il est affiché directement).
3. Clique sur **Nouveau secret** (*New Secret*) pour générer le **Client Secret** et copie-le **tout de suite** : il n'est affiché qu'une seule fois. Si tu le perds, clique de nouveau sur **Nouveau secret** (l'ancien ne fonctionnera plus).

Garde les deux sous la main pour l'étape suivante.

## Étape 4 : Lancer l'assistant d'installation

```bash
python setup.py
```

Colle ton Client ID et ton Client Secret quand il les demande. L'assistant ouvre ensuite ton navigateur : connecte-toi à Twitch avec le compte qui créera les clips et clique sur **Autoriser**. C'est terminé.

---

## Dépannage

| Problème | Solution |
|---|---|
| « Vous devez activer la 2FA » | Active l'authentification à deux facteurs sur ton compte Twitch, puis réessaie. |
| Nom déjà pris / refusé | Choisis un autre nom, sans le mot « Twitch ». |
| `redirect_uri mismatch` pendant l'autorisation | Dans ton app (Gérer), l'URL de redirection OAuth doit être exactement `http://localhost:3000`. |
| L'assistant indique que le port est déjà utilisé | Ferme le programme qui utilise le port 3000, puis relance `python setup.py`. |
| Le navigateur affiche « Authorization failed » | Vérifie que le Client ID et le Client Secret ont été copiés sans espace en trop. |

## Sécurité

- Ne partage jamais ton **Client Secret** ni ton fichier `.env`, et ne les publie jamais sur GitHub ou Discord.
- Si ton secret fuite, va dans ton app (Gérer) → **Nouveau secret**, puis relance `python setup.py`.
