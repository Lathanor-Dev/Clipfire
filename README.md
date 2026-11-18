# 🔥 Clipfire

🇬🇧 English · [🇫🇷 Français](README.fr.md)

**A bot that automatically clips the best moments of your Twitch stream.**
When chat goes wild, Clipfire creates a clip and posts the link in your Discord channel. Nothing to do on your side.

- 📈 Detects chat activity spikes (compared to the normal activity)
- 🎬 Creates the clip through the official Twitch API
- 💬 Posts the link to Discord with a simple webhook (no Discord bot to create)
- ⚙️ Adjustable thresholds, built-in anti-spam cooldown
- 🔑 Guided setup: the wizard gets your tokens for you

---

## Quick install

**Requirements:** [Python 3.10+](https://www.python.org/downloads/) and a Twitch account.

```bash
git clone https://github.com/Lathanor-Dev/Clipfire.git
cd Clipfire

# (recommended) virtual environment
python -m venv .venv
# Windows:        .venv\Scripts\activate
# Mac / Linux:    source .venv/bin/activate

pip install -r requirements.txt
python setup.py      # setup wizard
python bot.py        # start the bot
```

> On Mac/Linux, use `python3` if `python` doesn't work.

Keep `bot.py` running while you stream. That's it. 🎉

---

## What the wizard asks for (`setup.py`)

### 1. A Twitch app
📖 **[Detailed step-by-step guide](docs/twitch-app-guide.md)** (quick version below)

1. Go to [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) → **Register Your Application**.
2. **OAuth Redirect URL**: `http://localhost:3000`
3. **Category**: Chat Bot · **Client Type**: Confidential
4. Copy the **Client ID** and generate a **Client Secret**.

### 2. A private Discord channel + webhook
All clips are posted automatically in one Discord channel, so make it **private**: that way only you see the clips and you decide which ones are worth posting on social media.

1. Create a new channel and set it to **Private Channel** (Edit Channel → Permissions → turn on *Private Channel*), then add only yourself (and anyone you trust, like an editor or a mod).
2. In that channel: **Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL**.

> ⚠️ Anyone with the webhook URL can post in your channel, so keep it secret like your tokens.

### 3. Twitch authorization
The wizard opens your browser. Log in with the account that will create the clips (yours or a bot account) and click **Authorize**. Tokens are fetched and saved to `.env` automatically, and refreshed on their own afterwards.

---

## How it works

1. Clipfire reads your channel's chat (anonymous read-only, no access to your account).
2. It counts messages over a sliding window (10 s by default) and compares them to the average of the last 3 minutes.
3. If activity goes over the threshold (3× the average and at least 8 messages), it creates a clip.
4. The link is sent to Discord. A cooldown prevents duplicate clips.

## Full-stream analysis (highlights)

On top of instant clips, Clipfire **records the whole chat** during the stream (`logs/`). When the stream ends (≈ 3 min offline) it analyses everything and automatically clips the **best moments** from the VOD, then posts a ranked summary to Discord.

Signals combined (compared to *this stream's* normal): message rate, number of distinct chatters, "hype" messages (LUL, KEKW, lol, clip…), ALL-CAPS, subs / raids / bits.

```bash
python analyze.py logs/your_channel_123456.jsonl --dry-run   # preview moments, no clips created
python analyze.py logs/your_channel_123456.jsonl --top 5     # clip the 5 best
```

- Enable **"Store past broadcasts"** (VODs) in Twitch.
- `LIVE_CLIPS=0` turns off instant clips, `AUTO_ANALYZE=0` turns off automatic analysis. `HL_*` and `CLIP_*` settings are in `.env.example`.
- Clips from a VOD use Twitch's "Create Clip From VOD" API (open beta).
- With Docker, `logs/` is mounted so it survives restarts.

## Posting clips on social media

Each Discord message contains two links:

- ▶️ **Watch**: the normal clip link, to check if the moment is good.
- ✂️ **Edit / download**: the Twitch clip editor, where you can crop the clip to **vertical (9:16)** for TikTok, Reels or Shorts and download it.

The edit link gives access to the clip editor, which is why clips should go to a **private** channel (see step 2). Don't share that link publicly.

## Running it 24/7

Clipfire only creates clips while you're live, but you can leave it running all the time. It reconnects to chat by itself if the connection drops and refreshes its Twitch tokens on its own. Pick what suits you:

**Your own PC** (simplest): run `python bot.py` before going live. On Windows you can launch it at startup with the Task Scheduler.

**A Raspberry Pi or a small VPS** (always on):
1. Run `python setup.py` on your computer first (it needs a browser), then copy the generated `.env` file to the server.
2. Then choose one of these:

```bash
# Option A: Docker
docker compose up -d --build
docker compose logs -f        # see what the bot is doing

# Option B: systemd (Linux, without Docker)
# edit User and paths in clipfire.service first
sudo cp clipfire.service /etc/systemd/system/
sudo systemctl enable --now clipfire
journalctl -u clipfire -f
```

> Run **only one copy** of the bot at a time, otherwise you'll get duplicate clips.

## Settings

Everything is configured in the `.env` file:

| Variable | Default | Purpose |
|---|---|---|
| `WINDOW_SECONDS` | `10` | Length of the measured window |
| `BASELINE_SECONDS` | `180` | History used to compute normal activity |
| `SPIKE_MULTIPLIER` | `3` | The spike must be X times the normal level |
| `MIN_MESSAGES` | `8` | Minimum number of messages to trigger |
| `COOLDOWN_SECONDS` | `60` | Minimum delay between two clips |

**Too many clips?** Raise `SPIKE_MULTIPLIER` or `MIN_MESSAGES`.
**Not enough?** Lower them. For a small chat, `MIN_MESSAGES=4` is a good start.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Création du clip impossible : 404` | You're not live. Clips only work during a stream. |
| `401` / invalid token | Run `python setup.py` again to generate new tokens. |
| Nothing shows up in Discord | Check the webhook URL (the wizard sends a test message). |
| `redirect_uri mismatch` | Your Twitch app's redirect URL must be exactly `http://localhost:3000`. |
| The bot detects nothing | Lower `MIN_MESSAGES` and `SPIKE_MULTIPLIER` in `.env`. |

## Security

Your `.env` file contains your tokens: **never share it** and never commit it (it's already in `.gitignore`).

## Contributing

Issues and pull requests are welcome! Ideas: keyword detection (`KEKW`, `POG`…), manual `!clip` command, Docker image, posting the clip in Twitch chat.

## License

[MIT](LICENSE)
