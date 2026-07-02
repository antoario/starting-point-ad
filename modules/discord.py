import os
import tarfile
import asyncio
import discord
import re
from modules.base import BaseTask

CATEGORY_NAME = "a/d channels"
GENERAL_NAMES = {"general", "generale"}

def get_directory_names(tar_path: str) -> list[str]:
    """Helper to extract top-level directory names from a tar archive."""
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
    """Helper to sanitize directory names for Discord channel naming rules."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name

def find_available_category_name(guild: discord.Guild, base_name: str) -> str:
    """Finds an unused category name in the guild by appending a numeric suffix."""
    existing_names = {c.name for c in guild.categories}
    if base_name not in existing_names:
        return base_name
    suffix = 2
    while True:
        candidate = f"{base_name} {suffix}"
        if candidate not in existing_names:
            return candidate
        suffix += 1

def resolve_category(guild: discord.Guild, category_hint: str) -> discord.CategoryChannel | None:
    """Finds an existing category by its ID or name."""
    if category_hint.isdigit():
        cat = guild.get_channel(int(category_hint))
        if isinstance(cat, discord.CategoryChannel):
            return cat
        return None
    for cat in guild.categories:
        if cat.name.lower() == category_hint.lower():
            return cat
    return None

class DiscordConnectionManager:
    """Manages the Discord client connection lifecycle in the background."""

    def __init__(self, token: str, guild_id: int):
        self.token = token
        self.guild_id = guild_id
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.guild = None
        self.category = None
        self.general_channel = None
        self.ready_event = asyncio.Event()

        @self.client.event
        async def on_ready():
            print(f"[+] bot connected as {self.client.user}")
            self.guild = self.client.get_guild(self.guild_id)
            if self.guild is None:
                print(f"[error] guild with id {self.guild_id} not found or bot not in guild.")
            self.ready_event.set()

    async def start(self) -> None:
        """Starts the discord client connection loop."""
        try:
            await self.client.start(self.token)
        except asyncio.CancelledError:
            await self.close()

    async def wait_until_ready(self) -> None:
        """Waits until the bot is connected and ready."""
        await self.ready_event.wait()

    async def close(self) -> None:
        """Closes the discord connection safely."""
        if not self.client.is_closed():
            await self.client.close()
            print("[*] discord connection closed.")

class DiscordCategorySetupTask(BaseTask):
    """Task to resolve or create the Discord category channel."""

    def __init__(self, discord_manager: DiscordConnectionManager, category_hint: str | None = None):
        self.discord_manager = discord_manager
        self.category_hint = category_hint

    async def run(self) -> None:
        guild = self.discord_manager.guild
        if guild is None:
            raise RuntimeError("Discord client is not ready or guild not found.")

        if self.category_hint:
            category = resolve_category(guild, self.category_hint)
            if category is None:
                print(f"[error] could not find category '{self.category_hint}' in guild '{guild.name}'.")
                print(f"[hint]  available categories: {[c.name for c in guild.categories]}")
                raise ValueError(f"Category '{self.category_hint}' not found.")
            print(f"[*] using existing category '{category.name}' (id: {category.id})")
            self.discord_manager.category = category
        else:
            category_name = find_available_category_name(guild, CATEGORY_NAME)
            print(f"[*] creating category '{category_name}' in guild '{guild.name}' ({guild.id})...")
            category = await guild.create_category(category_name)
            await guild.create_voice_channel("voice", category=category)
            self.discord_manager.category = category

class DiscordChannelsSetupTask(BaseTask):
    """Task to create channels for service directories and the general channel."""

    def __init__(self, discord_manager: DiscordConnectionManager, service_dirs: list[str]):
        self.discord_manager = discord_manager
        self.service_dirs = service_dirs

    async def run(self) -> None:
        guild = self.discord_manager.guild
        category = self.discord_manager.category
        if guild is None or category is None:
            raise RuntimeError("Discord client is not ready or category not found.")

        # Resolve or create the general channel
        general_channel = next(
            (c for c in category.text_channels if c.name in GENERAL_NAMES), None
        )
        if general_channel is None:
            general_channel = await guild.create_text_channel("general", category=category)
        else:
            print(f"[*] using existing channel '#{general_channel.name}' for archive post.")
        self.discord_manager.general_channel = general_channel

        # Create service channels
        existing_channel_names = {c.name for c in category.channels}
        for name in self.service_dirs:
            safe_name = sanitize_channel_name(name)
            if not safe_name or safe_name in GENERAL_NAMES | {"voice"}:
                continue
            if safe_name in existing_channel_names:
                print(f"[*] skipping '#{safe_name}' — already exists.")
                continue
            print(f"[*] creating channel '#{safe_name}'...")
            await guild.create_text_channel(safe_name, category=category)

class DiscordArchiveUploaderTask(BaseTask):
    """Task to upload the local tar archive to the general channel."""

    def __init__(self, discord_manager: DiscordConnectionManager, local_tar: str):
        self.discord_manager = discord_manager
        self.local_tar = local_tar

    async def run(self) -> None:
        channel = self.discord_manager.general_channel
        if channel is None:
            print("[warning] no 'general' channel found — archive will not be posted.")
            return

        if not os.path.exists(self.local_tar):
            await channel.send(f"tar file '{self.local_tar}' not found on the bot host.")
            raise FileNotFoundError(f"Local tar archive '{self.local_tar}' not found.")

        print(f"[*] uploading archive to '#{channel.name}'...")
        await channel.send(content="enjoy hacking! 😄", file=discord.File(self.local_tar))
        print("[+] archive uploaded.")
