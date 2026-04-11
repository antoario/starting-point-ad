#!/usr/bin/env python3
import os
import tarfile
import asyncio
import discord
import re

BASE_CATEGORY_NAME = "a/d channels"

def get_directory_names(tar_path: str):
    if not os.path.exists(tar_path):
        raise FileNotFoundError(f"tar file '{tar_path}' not found.")

    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()

    top_level_dirs = set()

    for member in members:
        name = member.name.strip()
        if name.startswith("./"):
            name = name[2:]
        if not name or name in (".", ".."):
            continue
        parts = name.split("/")
        if member.isdir() and len(parts) == 1:
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


def resolve_category(guild: discord.Guild, category_hint: str) -> discord.CategoryChannel | None:
    """Find an existing category by ID (if numeric) or by name."""
    if category_hint.isdigit():
        cat = guild.get_channel(int(category_hint))
        if isinstance(cat, discord.CategoryChannel):
            return cat
        return None
    # name match (case-insensitive)
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
    ):
        super().__init__(intents=intents)
        self.tar_path = tar_path
        self.guild_id = guild_id
        self.token = token
        self.existing_category = existing_category

    async def setup_ad_category(self):
        guild = self.get_guild(self.guild_id)
        if guild is None:
            print(f"[error] guild with id {self.guild_id} not found or bot not in guild.")
            return

        dir_names = get_directory_names(self.tar_path)

        # resolve or create category
        if self.existing_category:
            category = resolve_category(guild, self.existing_category)
            if category is None:
                print(f"[error] could not find category '{self.existing_category}' in guild '{guild.name}'.")
                print(f"[hint]  available categories: {[c.name for c in guild.categories]}")
                return
            print(f"[*] using existing category '{category.name}' (id: {category.id})")
            create_defaults = False
        else:
            category_name = find_available_category_name(guild, BASE_CATEGORY_NAME)
            category = None
            create_defaults = True

        GENERAL_NAMES = {"general", "generale"}


        if create_defaults:
            print(f"[*] creating category '{category_name}' in guild '{guild.name}' ({guild.id})...")
            category = await guild.create_category(category_name)

            await guild.create_voice_channel("voice", category=category)

        # look for an existing general/generale channel in the category
        general_channel = next(
            (c for c in category.text_channels if c.name in GENERAL_NAMES), None
        ) if category else None

        if general_channel is None and create_defaults:
            general_channel = await guild.create_text_channel("general", category=category)
            await asyncio.sleep(DISCORD_CHANNEL_CREATE_DELAY)
        elif general_channel:
            print(f"[*] using existing channel '#{general_channel.name}' for archive post.")

        # create one channel per top-level directory
        existing_channel_names = {c.name for c in category.channels}
        for name in dir_names:
            safe_name = sanitize_channel_name(name)
            if not safe_name or safe_name in ("general", "generale", "voice"):
                continue
            if safe_name in existing_channel_names:
                print(f"[*] skipping '{safe_name}' — channel already exists.")
                continue
            await guild.create_text_channel(safe_name, category=category)
            await asyncio.sleep(DISCORD_CHANNEL_CREATE_DELAY)

        # post the archive
        if general_channel is None:
            print("[warning] no 'general' channel found in the category — archive will not be posted.")
            return

        if os.path.exists(self.tar_path):
            file_size_mb = os.path.getsize(self.tar_path) / (1024 * 1024)
            if file_size_mb > 25:
                print(f"[warning] tar file is {file_size_mb:.1f} MB — exceeds Discord's 25 MB limit for regular servers.")
            await general_channel.send(
                content="enjoy hacking! 😄",
                file=discord.File(self.tar_path)
            )
        else:
            await general_channel.send(
                f"tar file '{self.tar_path}' not found on the bot host."
            )

    async def on_ready(self):
        print(f"[+] bot connected as {self.user}")
        await self.setup_ad_category()
        await self.close()


async def run_full_flow(
    tar_path: str,
    guild_id: int,
    token: str,
    existing_category: str | None = None,
):
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