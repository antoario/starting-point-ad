# AD Discord Channel Generator

A Python tool for Attack & Defense CTF competitions. It connects to a remote VM via SSH, archives the target directory, downloads it locally, and automatically sets up a Discord server with a dedicated category and one channel per service.

---

## How It Works

1. Connects to the remote machine via SSH (password)
2. Creates a `.tar.gz` archive of all top-level directories in the configured remote path (dotfiles and loose files are excluded)
3. Downloads the archive locally via SCP and deletes the remote copy
4. Connects a Discord bot to your server and either creates a new category or reuses an existing one
5. Creates one text channel per top-level directory found in the archive
6. Uploads the archive to the `#general` (or `#generale`) channel

---

## Requirements

- Python 3.10+
- A Discord account with a server you manage or where you have permissions to  create categories, channels and send messages
- SSH access to the remote machine

Install dependencies:

```bash
pip install paramiko scp discord.py
```

Or inside a virtual environment:

```bash
python -m venv .venv && source .venv/bin/activate
pip install paramiko scp discord.py
```

---

## Project Structure

```
.
├── main.py        # Entry point: SSH flow + Discord bot orchestration
├── bot.py         # Discord bot: category and channel creation
├── config.ini     # Configuration (SSH + paths + Discord)
└── README.md
```

---

## Configuration

Edit `config.ini` before running:

```ini
[ssh]
host = ...
port = 22
username = root

[paths]
remote_dir = ~/
remote_tar = ~/backup.tar.gz
local_tar = backup.tar.gz

[discord]
guild_id = ...
; optional: reuse an existing category by name or numeric ID
; leave empty to create a new "a/d channels" category automatically
category =
```

### Secrets via environment variables

The SSH password and Discord bot token are never stored in `config.ini`. Export them before running:

```bash
export AD_SSH_PASSWORD="your-ssh-password"
export AD_DISCORD_TOKEN="your-bot-token"
```

---

## Discord Bot Setup

### 1. Create the Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. `ad-channel-gen`), click **Create**

### 2. Create the Bot and Copy the Token

1. In the left sidebar go to **Bot**
2. Click **Add Bot** → **Yes, do it!**
3. Under **TOKEN**, click **Reset Token** then **Copy**
4. Export it: `export AD_DISCORD_TOKEN="your-token-here"`

> **Warning:** never commit your token or share it. If accidentally exposed, immediately click **Reset Token** on the developer portal.

### 3. Enable Privileged Intents

Still in the **Bot** section, scroll to **Privileged Gateway Intents** and enable:

- **Server Members Intent**
- **Message Content Intent**

Click **Save Changes**.

### 4. Invite the Bot to Your Server

1. Go to **OAuth2 → URL Generator**
2. Under **Scopes** select `bot`
3. Under **Bot Permissions** select: `Manage Channels`, `Send Messages`, `Attach Files`
4. Copy the generated URL, open it in your browser, select your server and click **Authorise**

### 5. Get Your Guild ID

1. Open Discord → **Settings → Advanced → Developer Mode: ON**
2. Right-click your server name → **Copy Server ID**
3. Paste it into `config.ini` under `guild_id`

---

## Running

```bash
# full flow: SSH archive + Discord channels
./main.py

# only download the archive, skip Discord entirely
./main.py --mode tar

# use a different config file
./main.py --config /path/to/other.ini
```

### Expected output

```
[*] connecting to user@127.0.0.1:22 (key auth)
[+] ssh connection established.
[*] running remote command: ...
[+] remote tar created.
[*] downloading remote file '~/backup.tar.gz' to 'backup.tar.gz'
[+] download completed.
[+] remote tar deleted.
[*] ssh connection closed.
[*] starting discord bot flow
[+] bot connected as ad-channel-gen#1234
[*] creating category 'a/d channels' in guild 'My Server' (123456789)
[+] discord bot flow completed.
```

---

## Behaviour Notes

- **Category:** if no `category` is set in `config.ini` and a category named `a/d channels` already exists, the bot creates `a/d channels 2`, `a/d channels 3`, etc. to avoid conflicts.
- **Existing category:** if `category` is set, only the missing service channels are added — existing ones are skipped.
- **General channel:** if a channel named `general` or `generale` already exists in the category, it is reused and the archive is uploaded there. A new one is not created.
- **Archive size:** Discord's file upload limit is 25 MB for standard servers. The bot will warn you if the archive exceeds this before attempting the upload.
- **Dotfiles:** only top-level directories are archived. Dotfiles (`.bashrc`, `.ssh`, etc.) and loose files in the root are intentionally excluded.

---



## License

MIT License — you are free to use, modify, and distribute this project, but you must keep the original copyright notice.

Copyright (c) 2025 antoario