import os
import subprocess
import tarfile
import asyncio
import discord
import re

CATEGORY_NAME = "a/d channels"
MAX_FINDINGS = 50
SENSITIVE_PATTERN = re.compile(
    r'(password|passwd|pwd|secret.?key|secret|token|api.?key|private.?key|credential|key)'
    r'\s*[=:]\s*'
    r'(?:'
        r'["\'][^"\']{8,}["\']'
        r'|'
        r'[a-zA-Z0-9+/=_\-]{20,}'
    r')',
    re.IGNORECASE,
)
SKIP_EXTENSIONS = {'.pyc', '.pyo', '.class', '.o', '.so', '.a', '.bin', '.exe', '.dll'}
SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.tox', '.mypy_cache'}
EXCEPTION_LINE = re.compile(
    r'^(Traceback \(|  File "|During handling|[A-Za-z]+Error:|[A-Za-z]+Exception:|[A-Za-z]+Warning:|\s+File ".*", line \d+)'
)


def get_directory_names(tar_path: str) -> list[str]:
    if not os.path.exists(tar_path):
        raise FileNotFoundError(f"tar file '{tar_path}' not found.")

    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
    top_level_dirs: set[str] = set()

    for m in members:
        name = m.name.strip()
        if name.startswith("./"):
            name = name[2:]
        if not name or name in (".", ".."):
            continue
        parts = name.split("/")
        if m.isdir() and len(parts) == 1:
            clean = parts[0].strip()
            if not clean or clean.startswith("."):
                continue
            top_level_dirs.add(clean)

    return sorted(top_level_dirs)


def sanitize_channel_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name


def find_available_category_name(guild: discord.Guild, base_name: str) -> str:
    existing_names = {c.name for c in guild.categories}
    if base_name not in existing_names:
        return base_name
    suffix = 2
    while True:
        candidate = f"{base_name} {suffix}"
        if candidate not in existing_names:
            return candidate
        suffix += 1


def resolve_category(
    guild: discord.Guild, category_hint: str
) -> discord.CategoryChannel | None:
    if category_hint.isdigit():
        cat = guild.get_channel(int(category_hint))
        if isinstance(cat, discord.CategoryChannel):
            return cat
        return None
    for cat in guild.categories:
        if cat.name.lower() == category_hint.lower():
            return cat
    return None


class AdBot(discord.Client):
    def __init__(
        self,
        tar_path: str,
        guild_id: int,
        token: str,
        existing_category: str | None = None,
        *,
        intents: discord.Intents,
    ) -> None:
        super().__init__(intents=intents)
        self.tar_path = tar_path
        self.guild_id = guild_id
        self.token = token
        self.existing_category = existing_category

    async def setup_ad_category(self) -> None:
        guild = self.get_guild(self.guild_id)
        if guild is None:
            print(f"[error] guild with id {self.guild_id} not found or bot not in guild.")
            return

        dir_names = get_directory_names(self.tar_path)
        GENERAL_NAMES = {"general", "generale"}

        if self.existing_category:
            category = resolve_category(guild, self.existing_category)
            if category is None:
                print(f"[error] could not find category '{self.existing_category}' in guild '{guild.name}'.")
                print(f"[hint]  available categories: {[c.name for c in guild.categories]}")
                return
            print(f"[*] using existing category '{category.name}' (id: {category.id})")
            create_defaults = False
        else:
            category_name = find_available_category_name(guild, CATEGORY_NAME)
            print(f"[*] creating category '{category_name}' in guild '{guild.name}' ({guild.id})...")
            category = await guild.create_category(category_name)
            await guild.create_voice_channel("voice", category=category)
            create_defaults = True

        general_channel = next(
            (c for c in category.text_channels if c.name in GENERAL_NAMES), None
        )

        if general_channel is None and create_defaults:
            general_channel = await guild.create_text_channel("general", category=category)
        elif general_channel:
            print(f"[*] using existing channel '#{general_channel.name}' for archive post.")

        existing_channel_names = {c.name for c in category.channels}
        for name in dir_names:
            safe_name = sanitize_channel_name(name)
            if not safe_name or safe_name in GENERAL_NAMES | {"voice"}:
                continue
            if safe_name in existing_channel_names:
                print(f"[*] skipping '#{safe_name}' — already exists.")
                continue
            print(f"[*] creating channel '#{safe_name}'...")
            await guild.create_text_channel(safe_name, category=category)

        if general_channel is None:
            print("[warning] no 'general' channel found — archive will not be posted.")
            return

        if os.path.exists(self.tar_path):
            await self.upload_file(general_channel)
        else:
            await general_channel.send(f"tar file '{self.tar_path}' not found on the bot host.")

    async def upload_file(self, channel: discord.TextChannel) -> None:
        print(f"[*] uploading archive to '#{channel.name}'...")
        await channel.send(content="enjoy hacking! 😄", file=discord.File(self.tar_path))
        print("[+] archive uploaded.")
        await self.scan_and_report(channel)

    def _do_scan(self) -> tuple[list[str], int]:
        scan_dirs = [d for d in get_directory_names(self.tar_path) if os.path.isdir(d)]
        if not scan_dirs:
            return [], 0

        cmd = [
            "grep", "-rniP",
            (
                r'(password|passwd|pwd|secret.?key|secret|token|api.?key|private.?key|credential|key)'
                r'\s*[=:]\s*'
                r'(?:["\'][^"\']{8,}["\']|[a-zA-Z0-9+/=_\-]{20,})'
            ),
        ]
        for d in SKIP_DIRS:
            cmd.append(f"--exclude-dir={d}")
        for e in SKIP_EXTENSIONS:
            cmd.append(f"--exclude=*{e}")
        cmd += scan_dirs

        result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")

        findings: list[str] = []
        total = 0
        for raw in result.stdout.splitlines():
            parts = raw.split(":", 2)
            if len(parts) < 3:
                continue
            fpath, lineno, line = parts
            if EXCEPTION_LINE.match(line):
                continue
            match = SENSITIVE_PATTERN.search(line)
            if match:
                pre = line[:match.start()].rstrip()
                if pre.endswith(("(", ",")):
                    continue
            total += 1
            if len(findings) < MAX_FINDINGS:
                findings.append(f"`{fpath}:{lineno}` {line.strip()}")

        return findings, total

    async def _send_text(self, channel: discord.TextChannel, content: str) -> None:
        try:
            await asyncio.wait_for(channel.send(content), timeout=30.0)
        except asyncio.TimeoutError:
            print("[warning] channel.send timed out, skipping chunk.")
        except Exception as e:
            print(f"[warning] channel.send failed: {e}")

    async def scan_and_report(self, channel: discord.TextChannel) -> None:
        print("[*] scanning archive for sensitive keywords...")
        findings, total = await asyncio.to_thread(self._do_scan)
        print(f"[*] scan complete: {total} match(es) found.")
        if not findings:
            await self._send_text(channel, "🔍 no sensitive keywords found in archive.")
            return

        chunk = "🔍 **sensitive keywords found**:\n"
        for entry in findings:
            line = entry + "\n"
            if len(chunk) + len(line) > 1900:
                await self._send_text(channel, chunk)
                chunk = line
            else:
                chunk += line
        if chunk:
            await self._send_text(channel, chunk)

    async def on_ready(self) -> None:
        print(f"[+] bot connected as {self.user}")
        try:
            await self.setup_ad_category()
        except Exception as e:
            print(f"[error] setup failed: {e}")
        finally:
            await self.close()


async def run_full_flow(
    tar_path: str,
    guild_id: int,
    token: str,
    existing_category: str | None = None,
) -> None:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    client = AdBot(
        tar_path=tar_path,
        guild_id=guild_id,
        token=token,
        existing_category=existing_category,
        intents=intents,
    )
    try:
        await client.login(client.token)
        await client.connect()
    finally:
        if not client.is_closed():
            await client.close()