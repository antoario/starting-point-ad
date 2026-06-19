# Starting Point AD

A Python tool for Attack & Defense CTF competitions. It connects to a remote VM via SSH, archives the target directory, downloads it locally, automatically sets up a Discord server with a dedicated category and one channel per service, and scans the archive for sensitive credentials.

---

## How It Works

1. Connects to the remote machine via SSH (password auth)
2. Creates a `.tar.gz` archive of all top-level directories in the configured remote path (dotfiles and loose files are excluded)
3. Downloads the archive locally via SCP and deletes the remote copy
4. Extracts the archive into a local directory (`git_dir`, default: `ad/`), runs `git init` inside it, stages all files and creates an initial commit — giving you a versioned snapshot of the remote services
5. Connects a Discord bot to your server and either creates a new category or reuses an existing one
6. Creates one text channel per top-level directory found in the archive
7. Uploads the archive to the `#general` (or `#generale`) channel
8. Scans every file in the archive for sensitive keywords (`password`, `passwd`, `pwd`, `secret`, `token`, `api_key`, `private_key`, `credential`, `keys`) and posts each match with its file path and line number to `#general`; if nothing is found, posts a "no results" notice instead

---

## Requirements

- Python 3.10+
- A Discord account with a server you manage, or where you have permission to create channels, categories and send messages
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
host=127.0.0.1
port=22
username=root

[paths]
remote_dir=~/
remote_tar=~/backup.tar.gz
local_tar=backup.tar.gz
git_dir=ad

[discord]
guild_id=...
; optional: reuse an existing category by name or numeric ID
; leave empty to create a new "a/d channels" category automatically
category=
```

### Secrets via environment variables

The SSH password and Discord bot token are never stored in `config.ini`. Export them before running:

```bash
export AD_SSH_PASSWD="your-ssh-password"
export AD_DS_TOKEN="your-bot-token"
```

---

## Discord Bot Setup

### 1. Create the Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. `starting-point-ad`), click **Create**

### 2. Create the Bot and Copy the Token

1. In the left sidebar go to **Bot**
2. Click **Add Bot** → **Yes, do it!**
3. Under **TOKEN**, click **Reset Token** then **Copy**
4. Export it: `export AD_DS_TOKEN="your-token-here"`

>  [!CAUTION]
> Never commit your token or share it. If accidentally exposed, immediately click **Reset Token** on the developer portal.

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
./main.py
```

### Expected output

```
[*] connecting to user@127.0.0.1:22
[+] ssh connection established.
[*] running remote command: ...
[+] remote tar created.
[*] downloading remote file '~/backup.tar.gz' to 'backup.tar.gz'
[+] download completed.
[+] remote tar deleted.
[*] ssh connection closed.
[*] initializing git repo in 'ad'...
[+] git repo initialized and initial snapshot committed.
[*] starting discord bot flow
[+] bot connected as starting-point-ad#1234
[*] creating category 'a/d channels' in guild 'My Server' (123456789)
[*] uploading archive to '#general'...
[+] archive uploaded.
[*] scanning archive for sensitive keywords...
[*] scan complete: 3 match(es) found.
[+] discord bot flow completed.
```

---

## Behaviour Notes

- **Category:** if no `category` is set in `config.ini` and a category named `a/d channels` already exists, the bot creates `a/d channels 2`, `a/d channels 3`, etc. to avoid conflicts.
- **Existing category:** if `category` is set, only the missing service channels are added — existing ones are skipped.
- **General channel:** if a channel named `general` or `generale` already exists in the category, it is reused and the archive is uploaded there. A new one is not created.
- **Dotfiles:** only top-level directories are archived. Dotfiles (`.bashrc`, `.ssh`, etc.) and loose files in the root are intentionally excluded.
- **Keyword scan:** after the upload, every file in the archive is scanned for sensitive strings (`password`, `passwd`, `pwd`, `secret`, `token`, `api_key`, `private_key`, `credential`, `key`). Each match is reported in `#general` as `` `path/to/file:42` matched line ``.

---

## License

MIT License — you are free to use, modify, and distribute this project, but you must keep the original copyright notice.

Copyright (c) 2025 antoario