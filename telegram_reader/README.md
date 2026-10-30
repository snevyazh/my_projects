# Telegram Reader

A read-only command-line tool for browsing Telegram cloud chats that **your own account can already access**. It uses Telegram's MTProto user API through Telethon; it is not a bot.

## What it can access

- Channels you joined, including their available history
- Groups, supergroups, direct messages, and Saved Messages
- Public channels by username when Telegram allows your account to resolve them

It cannot bypass private-channel membership, deleted content, admin restrictions, or Telegram permissions. Secret Chats are end-to-end encrypted and device-specific, so they are not available through Telethon.

## Setup (Windows PowerShell)

1. Install Python 3.10 or newer.
2. Visit [my.telegram.org/apps](https://my.telegram.org/apps), create an application, and copy its `api_id` and `api_hash`.
3. In this directory, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

4. Edit `.env` and enter your API ID and API hash.
5. List your dialogs:

```powershell
python telegram_reader.py dialogs
```

On the first run, Telethon asks for your phone number, a code delivered by Telegram, and your 2FA password if enabled. It then creates a local session under `sessions/`; treat that file like a password and never share it.

## Commands

```powershell
# List recent dialogs (add --all for archived dialogs)
python telegram_reader.py dialogs --limit 200

# Read the latest 50 messages by numeric ID, username, or exact title
python telegram_reader.py messages -1001234567890 --limit 50
python telegram_reader.py messages @channelname --limit 50
python telegram_reader.py messages "Exact Channel Title" --limit 50

# Filter within one chat; output machine-readable JSON Lines
python telegram_reader.py messages @channelname --search "release" --json

# Search across all accessible dialogs
python telegram_reader.py search "release notes" --limit 100

# Export up to 5,000 messages, oldest first
python telegram_reader.py export @channelname --limit 5000 --output exports/channel.json

# Download the complete available history, including photos and videos
python telegram_reader.py download -1001421782518

# Or download only the newest 500 messages to a chosen directory
python telegram_reader.py download -1001421782518 --limit 500 --output downloads/my_channel
```

Before downloading, the command reports the channel's overall message count and then displays a `tqdm` progress bar. The default download directory is named after the channel (with characters that Windows forbids in folder names replaced by `_`). It contains `messages.json` plus media grouped into `photos/`, `videos/`, `audio/`, `documents/`, `gifs/`, `stickers/`, and `other/`. Each filename starts with its Telegram message ID, making paths stable across repeated downloads; existing media is reused. Use `--output` to override the folder.

Run `python telegram_reader.py --help` or add `--help` after a command for all options.

## Security and API limits

- `.env`, session files, and exports are ignored by Git.
- The program only reads; it contains no send, edit, join, or delete command.
- Telegram may rate-limit large history reads. Keep request volumes reasonable and comply with Telegram's API Terms of Service.
- To revoke the session, use Telegram **Settings → Devices** and terminate it, then delete the local `sessions` directory.
