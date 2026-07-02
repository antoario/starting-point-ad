#!/usr/bin/env python3
import configparser
import sys
import asyncio
import os

from ssh_client import SSHClientWrapper
from modules.remote_tasks import RemoteTarCreatorTask, SCPDownloadTask, RemoteCleanupTask
from modules.git import TarExtractorTask, GitInitializerTask
from modules.discord import (
    DiscordConnectionManager,
    DiscordCategorySetupTask,
    DiscordChannelsSetupTask,
    DiscordArchiveUploaderTask,
    get_directory_names,
)
from modules.scan import CredentialScannerTask, DiscordReportSenderTask

CONFIG_FILE = "config.ini"


def load_config(path: str) -> tuple:
    config = configparser.ConfigParser()
    read_files = config.read(path)
    if not read_files:
        raise FileNotFoundError(f"config file '{path}' not found.")

    for section in ("ssh", "git", "discord"):
        if section not in config:
            raise ValueError(f"section [{section}] missing in '{path}'.")

    # [ssh]
    ssh_conf = config["ssh"]
    host = ssh_conf.get("host", "").strip()
    username = ssh_conf.get("username", "").strip()
    port = ssh_conf.get("port", "22").strip()
    remote_dir = ssh_conf.get("remote_dir", "~").strip()
    remote_tar = ssh_conf.get("remote_tar", "~/backup.tar.gz").strip()
    password = os.environ.get("AD_SSH_PASSWD", "").strip() or None

    if not host or not username:
        raise ValueError("missing one or more required fields in [ssh]: host,username.")
    if not password:
        raise ValueError("AD_SSH_PASSWD environment variable is not set.")
    try:
        port = int(port)
    except ValueError:
        raise ValueError("[ssh] port must be an integer.")

    # [git]
    git_conf = config["git"]
    local_tar = git_conf.get("local_tar", "backup.tar.gz").strip()
    git_dir = git_conf.get("git_dir", "ad").strip() or "ad"

    # [discord]
    ds_conf = config["discord"]
    guild_id_str = ds_conf.get("guild_id", "").strip()
    category = ds_conf.get("category", "").strip() or None
    token = os.environ.get("AD_DS_TOKEN", "").strip()

    if not guild_id_str:
        raise ValueError("[discord] guild_id is required in config file.")
    if not token:
        raise ValueError("AD_DS_TOKEN environment variable is not set.")
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        raise ValueError("[discord] guild_id must be an integer.")

    return host, port, username, password, remote_dir, remote_tar, local_tar, git_dir, guild_id, token, category


async def async_main() -> None:
    try:
        host, port, username, password, remote_dir, remote_tar, local_tar, git_dir, guild_id, token, category = load_config(
            CONFIG_FILE
        )
    except Exception as e:
        print(f"[error] config error: {e}")
        sys.exit(1)

    # 1. Instantiate Discord Connection Manager and start connection in background
    discord_manager = DiscordConnectionManager(token, guild_id)
    discord_connect_task = asyncio.create_task(discord_manager.start())

    try:
        # 2. Start SSH connection and download pipeline
        ssh_client = SSHClientWrapper(host, port, username, password)
        
        async def run_ssh_flow():
            try:
                await asyncio.to_thread(ssh_client.connect)
                
                # Remote archiving tasks
                tar_task = RemoteTarCreatorTask(ssh_client, remote_dir, remote_tar)
                download_task = SCPDownloadTask(ssh_client, remote_tar, local_tar)
                cleanup_task = RemoteCleanupTask(ssh_client, remote_tar)

                await tar_task.run()
                await download_task.run()
                await cleanup_task.run()
            finally:
                ssh_client.close()

        ssh_task = asyncio.create_task(run_ssh_flow())

        # Wait for SSH download task to finish and Discord connection to be established
        await ssh_task
        await discord_manager.wait_until_ready()

        # 3. Git extraction & commit AND Discord channel setup in parallel
        service_dirs = get_directory_names(local_tar)

        git_extractor = TarExtractorTask(local_tar, git_dir)
        git_initializer = GitInitializerTask(git_dir)

        async def run_git_flow():
            await git_extractor.run()
            await git_initializer.run()

        discord_category_setup = DiscordCategorySetupTask(discord_manager, category)
        discord_channels_setup = DiscordChannelsSetupTask(discord_manager, service_dirs)
        discord_archive_uploader = DiscordArchiveUploaderTask(discord_manager, local_tar)

        async def run_discord_setup_flow():
            await discord_category_setup.run()
            await discord_channels_setup.run()
            await discord_archive_uploader.run()

        git_task = asyncio.create_task(run_git_flow())
        discord_setup_task = asyncio.create_task(run_discord_setup_flow())

        await asyncio.gather(git_task, discord_setup_task)

        # 4. Scanner and Report
        print("[*] starting credential scanning flow...")
        scanner_task = CredentialScannerTask(git_dir, local_tar)
        await scanner_task.run()

        report_task = DiscordReportSenderTask(discord_manager, scanner_task.findings, scanner_task.total)
        await report_task.run()

        print("[+] pipeline execution completed successfully.")

    except Exception as e:
        print(f"[error] pipeline execution failed: {e}")
    finally:
        # 5. Safe disposal of Discord client connection
        await discord_manager.close()
        try:
            await discord_connect_task
        except Exception:
            pass


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[info] process interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
