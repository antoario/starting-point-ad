import os
import tarfile
import discord

TOKEN = "YOUR_TOKEN_HERE"
BASE_CATEGORY_NAME = "a/d channels"


def get_directory_names(tar_path: str):
    if not os.path.exists(tar_path):
        raise FileNotFoundError(f"tar file '{tar_path}' not found.")
    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
    top_level_dirs = set()
    for member in members:
        name = member.name
        if name.startswith("./"):
            name = name[2:]
        if not name:
            continue
        parts = name.split("/")
        if member.isdir() and len(parts) == 1:
            top_level_dirs.add(parts[0])
    return sorted(top_level_dirs)


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


class ad_bot(discord.Client):
    def __init__(self, tar_path: str, guild_id: int, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tar_path = tar_path
        self.guild_id = guild_id

    async def setup_ad_category(self):
        guild = self.get_guild(self.guild_id)
        if guild is None:
            print(f"[error] guild with id {self.guild_id} not found or bot is not in that guild.")
            return

        dir_names = get_directory_names(self.tar_path)
        category_name = find_available_category_name(guild, BASE_CATEGORY_NAME)

        print(f"[*] creating category '{category_name}' in guild '{guild.name}' ({guild.id})...")
        category = await guild.create_category(category_name)
        await guild.create_voice_channel("voice", category=category)
        general_channel = await guild.create_text_channel("general", category=category)

        for name in dir_names:
            safe_name = name.lower()
            if not safe_name or safe_name == "general":
                continue
            await guild.create_text_channel(safe_name, category=category)

        if os.path.exists(self.tar_path):
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


async def run_full_flow(tar_path: str, guild_id: int):
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    client = ad_bot(tar_path=tar_path, guild_id=guild_id, intents=intents)
    try:
        await client.login(TOKEN)
        await client.connect()
    finally:
        if not client.is_closed():
            await client.close()
        http = getattr(client, "http", None)
        session = getattr(http, "_HTTPClient__session", None) if http else None
        if session is not None and not session.closed:
            await session.close()