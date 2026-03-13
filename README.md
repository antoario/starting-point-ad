# AD Discord Channel Generator

A Python tool that connects to a remote server via SSH, creates a compressed archive of a target directory, downloads it locally, and then automatically sets up a Discord server with a dedicated category and text channels named after the top-level directories found inside the archive.

Built for Attack & Defense CTF competitions.

---

## How It Works

1. Connects to a remote machine via SSH
2. Creates a `.tar.gz` archive of the configured remote directory
3. Downloads the archive locally via SCP
4. Deletes the remote archive
5. Connects a Discord bot to your server
6. Creates an `a/d channels` category with:
   - A `#general` text channel (the archive is uploaded here)
   - A `voice` voice channel
   - One text channel per top-level directory found in the archive

---

## Requirements

- Python 3.8+
- A Discord account with a server you manage
- SSH access to a remote machine

Install dependencies:
```bash
sudo apt install python3-paramiko python3-scp python3-discord
```
or

```bash
pip install paramiko scp discord.py
```

---

## Project Structure

```
.
├── main.py        # SSH flow: connect, archive, download, cleanup
├── bot.py         # Discord bot: create category and channels
├── config.ini     # Configuration file (SSH + paths + Discord)
└── README.md
```

---

## Configuration

Edit `config.ini` before running:

```ini
[ssh]
host = 127.0.0.1       ; IP address of the remote machine
port = 22              ; SSH port (default: 22)
username = ...         ; SSH username
password = ...         ; SSH password

[paths]
remote_dir = ~/          ; Directory to archive on the remote machine
remote_tar = ~/backup.tar.gz  ; Where to save the archive on the remote machine
local_tar = backup.tar.gz         ; Local filename for the downloaded archive

[discord]
guild_id = ...         ; ID of your Discord server (see setup guide below)
```

---

## Discord Bot Setup

### 1. Create the Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. `ad-channel-gen`), and click **Create**

### 2. Create the Bot and Copy the Token

1. In the left sidebar, go to **Bot**
2. Click **Add Bot** → **Yes, do it!**
3. Under **TOKEN**, click **Reset Token** then **Copy**
4. Paste the token in `bot.py`:

```python
TOKEN = "YOUR_TOKEN_HERE"
```

> **Warning:** never share your token or commit it to a public repository. If you accidentally expose it, immediately click **Reset Token** on the developer portal.

### 3. Enable Privileged Intents

Still in the **Bot** section, scroll down to **Privileged Gateway Intents** and enable:

- **Server Members Intent**
- **Message Content Intent**

Click **Save Changes**.

### 4. Invite the Bot to Your Server

1. In the left sidebar, go to **OAuth2 → URL Generator**
2. Under **Scopes**, select `bot`
3. Under **Bot Permissions**, select:
   - `Manage Channels`
   - `Send Messages`
   - `Attach Files`
4. Copy the generated URL at the bottom of the page, open it in your browser
5. Select your server from the dropdown and click **Authorise**

### 5. Get Your Guild ID

1. Open Discord → **Settings → Advanced → Developer Mode: ON**
2. Right-click your server name → **Copy Server ID**
3. Paste it into `config.ini` under `guild_id`

---

## Running

Once `config.ini` is filled in and the bot has been added to your server:

```bash
python main.py
```

Expected output:

```
[*] connecting to user@127.0.0.1:22
[+] ssh connection established.
[*] running remote command: bash -lc 'cd ~/ && tar -czf ~/backup.tar.gz .'
[+] remote tar created.
[*] downloading remote file '~/backup.tar.gz' to 'backup.tar.gz'
[+] download completed.
[+] remote tar deleted.
[*] ssh connection closed.
[*] starting discord bot flow...
[+] bot connected as AD-Bot#1234
[*] creating category 'a/d channels' in guild 'My Server'
[+] discord bot flow completed.
```

---

## Notes

- If an `a/d channels` category already exists in the server, the bot will automatically create `a/d channels 2`, `a/d channels 3`, etc. to avoid conflicts.
- Channel names are taken from the directory names as-is, only lowercased to comply with Discord's requirements.

---

## Security

- Do **not** commit `config.ini` or `bot.py` with real credentials to a public repository.
- Add them to `.gitignore`:

```
config.ini
bot.py
backup.tar.gz
```
