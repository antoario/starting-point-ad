import os
import zipfile
import discord

TOKEN = ...
BASE_CATEGORY_NAME = "A/D"


def get_directory_names(zip_path: str):
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Zip file '{zip_path}' not found.")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
    
    top_level_dirs = set()

    for name in names:
        if name.endswith("/"):
            parts = name.split("/")
            if len(parts) >= 2:
                top_level_dirs.add(parts[0])
        else:
            parts = name.split("/")
            if len(parts) >= 2:
                top_level_dirs.add(parts[0])

    sorted_dirs = sorted(top_level_dirs)
    return sorted_dirs


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


class ADBot(discord.Client):
    def __init__(self, zip_path: str, guild_id: int, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.zip_path = zip_path
        self.guild_id = guild_id

    async def setup_ad_category(self):
        guild = self.get_guild(self.guild_id)

        if guild is None:
            print(f"[ERROR] Guild with ID {self.guild_id} not found or bot is not in that guild.")
            return

        dir_names = get_directory_names(self.zip_path)
        category_name = find_available_category_name(guild, BASE_CATEGORY_NAME)
        print(f"[*] Creating category '{category_name}' in guild '{guild.name}'({guild.id})...")
        category = await guild.create_category(category_name)
        voice_channel = await guild.create_voice_channel("voice", category=category)
        general_channel = await guild.create_text_channel("general", category=category)
        created_text_channels = [general_channel.mention]

        for name in dir_names:
            safe_name = name.lower().replace(" ", "-")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in ["-", "_"])

            if not safe_name:
                continue

            if safe_name == "general":
                continue

            channel = await guild.create_text_channel(safe_name, category=category)
            created_text_channels.append(channel.mention)

        if os.path.exists(self.zip_path):
            await general_channel.send(
                content="Enjoy hacking! 😄",
                file=discord.File(self.zip_path)
            )
        else:
            await general_channel.send(
                f"Zip file '{self.zip_path}' not found on the bot host."
            )

    async def on_ready(self):
        print(f"[+] Bot connected as {self.user}")
        await self.setup_ad_category()
        await self.close()

async def run_full_flow(zip_path: str, guild_id: int):
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    client = ADBot(zip_path=zip_path, guild_id=guild_id, intents=intents)

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