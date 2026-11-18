# Creating your Twitch app (step by step)

🇬🇧 English · [🇫🇷 Français](twitch-app-guide.fr.md)

Clipfire needs a small "app" registered on Twitch. It's free, takes about 2 minutes, and gives you two values: a **Client ID** and a **Client Secret**. The setup wizard (`python setup.py`) will ask you for them.

> The Twitch developer console may change slightly over time. The names below are the ones used at the time of writing.

---

## Before you start

- You need a **Twitch account** (the one you stream with, or any account).
- Twitch requires **two-factor authentication (2FA)** on your account to register an app. If it isn't enabled yet, go to Twitch → Settings → Security and Privacy → *Two-Factor Authentication Setup*.

## Step 1: Open the developer console

1. Go to **https://dev.twitch.tv/console/apps**
2. Log in with your Twitch account. If it's your first time, accept the developer terms.

## Step 2: Register the application

Click **Register Your Application** and fill in the form:

| Field | What to put |
|---|---|
| **Name** | Any unique name, for example `Clipfire-yourpseudo`. It must be unique across Twitch and can't contain the word "Twitch". |
| **OAuth Redirect URLs** | `http://localhost:3000` then click **Add**. It must be exactly this, with no trailing slash. |
| **Category** | `Chat Bot` |
| **Client Type** | `Confidential` |

Then click **Create** (you may have to solve a captcha).

## Step 3: Get your Client ID and Client Secret

1. Your app now appears in the list. Click **Manage**.
2. Copy the **Client ID** (it's shown right away).
3. Click **New Secret** to generate the **Client Secret** and copy it **immediately**: it's only shown once. If you lose it, click **New Secret** again (the old one stops working).

Keep both somewhere handy for the next step.

## Step 4: Run the setup wizard

```bash
python setup.py
```

Paste your Client ID and Client Secret when asked. The wizard then opens your browser: log in to Twitch with the account that will create the clips and click **Authorize**. You're done.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "You must enable 2FA" | Enable two-factor authentication on your Twitch account, then try again. |
| "Name is already taken" / name refused | Choose another name, and don't use "Twitch" in it. |
| `redirect_uri mismatch` during authorization | In your app (Manage), the OAuth Redirect URL must be exactly `http://localhost:3000`. |
| The wizard says the port is already in use | Close the program using port 3000, then run `python setup.py` again. |
| Browser shows "Authorization failed" | Check that the Client ID and Client Secret were copied without extra spaces. |

## Security

- Never share your **Client Secret** or your `.env` file, and never post them on GitHub or Discord.
- If your secret leaks, go to your app (Manage) → **New Secret**, then run `python setup.py` again.
