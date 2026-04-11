#!/usr/bin/env python3
import configparser
import paramiko
from scp import SCPClient
import sys
import asyncio
import os
import argparse
from bot import run_full_flow

CONFIG_FILE = "config.ini"


def load_config(path: str, discord_required: bool = True):
    config = configparser.ConfigParser()
    read_files = config.read(path, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(f"config file '{path}' not found.")

    required_sections = ("ssh", "paths", "discord") if discord_required else ("ssh", "paths")
    for section in required_sections:
        if section not in config:
            raise ValueError(f"section [{section}] missing in '{path}'.")

    # ssh
    ssh_conf = config["ssh"]
    host = ssh_conf.get("host", "").strip()
    username = ssh_conf.get("username", "").strip()
    port_str = ssh_conf.get("port", "22").strip()
    key_path = ssh_conf.get("key_path", "").strip() or None

    password = os.environ.get("AD_SSH_PASSWORD", "").strip() or None

    if not host or not username:
        raise ValueError("missing one or more required fields in [ssh]: host, username")
    if not key_path and not password:
        raise ValueError(
            "no SSH auth method configured: or export AD_SSH_PASSWORD"
        )
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError("[ssh] port must be an integer")

    # Paths
    paths_conf = config["paths"]
    remote_dir = paths_conf.get("remote_dir", "~").strip()
    remote_tar = paths_conf.get("remote_tar", "~/backup.tar.gz").strip()
    local_tar = paths_conf.get("local_tar", "backup.tar.gz").strip()

    # Discord (only validated when discord_required=True)
    guild_id = None
    token = None
    category = None
    if discord_required:
        discord_conf = config["discord"]
        guild_id_str = discord_conf.get("guild_id", "").strip()
        token = os.environ.get("AD_DISCORD_TOKEN", "").strip()

        if not guild_id_str:
            raise ValueError("[discord] guild_id is required in config.ini")
        if not token:
            raise ValueError("AD_DISCORD_TOKEN environment variable is not set")
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            raise ValueError("[discord] guild_id must be an integer")

        category = discord_conf.get("category", "").strip() or None

    return host, port, username, password, key_path, remote_dir, remote_tar, local_tar, guild_id, token, category


def create_ssh_client(
    host: str,
    port: int,
    username: str,
    password: str | None,
    key_path: str | None,
) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = dict(
        hostname=host,
        port=port,
        username=username,
        timeout=10,
    )

    if key_path:
        print(f"[*] connecting to {username}@{host}:{port} (key auth: {key_path})")
        connect_kwargs["key_filename"] = key_path
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False
    else:
        print(f"[*] connecting to {username}@{host}:{port} (password auth)")
        connect_kwargs["password"] = password
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False

    client.connect(**connect_kwargs)
    print("[+] ssh connection established.")
    return client


def run_remote_command(ssh_client: paramiko.SSHClient, command: str):
    import shlex
    wrapped_cmd = f"bash -lc {shlex.quote(command)}"
    print(f"[*] running remote command: {wrapped_cmd}")
    _, stdout, stderr = ssh_client.exec_command(wrapped_cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err


def create_remote_tar(ssh_client: paramiko.SSHClient, remote_dir: str, remote_tar: str):
    cmd = (
        f"cd {remote_dir} && "
        f"find . -maxdepth 1 -mindepth 1 -type d ! -name '.*' -printf '%P\\n' | "
        f"tar --warning=no-file-changed -czf {remote_tar} -T -"
    )
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        if "file changed as we read it" not in err:
            raise RuntimeError(f"error creating remote tar: {err}")
    print("[+] remote tar created.")


def download_remote_file(ssh_client: paramiko.SSHClient, remote_path: str, local_path: str):
    print(f"[*] downloading remote file '{remote_path}' to '{local_path}'")
    with SCPClient(ssh_client.get_transport()) as scp:
        scp.get(remote_path, local_path=local_path)
    print("[+] download completed.")


def delete_remote_file(ssh_client: paramiko.SSHClient, remote_path: str):
    cmd = f"rm -f {remote_path}"
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        raise RuntimeError(f"error deleting remote file: {err}")
    print("[+] remote tar deleted.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A/D CTF tool: archive remote VM home dir and publish to Discord."
    )
    parser.add_argument(
        "--mode",
        choices=["tar", "full"],
        default="full",
        help=(
            "'tar'  — SSH into the VM, create and download the archive, then stop. "
            "'full' — do everything: tar + download + create Discord channels (default)."
        ),
    )
    parser.add_argument(
        "--config",
        default=CONFIG_FILE,
        metavar="PATH",
        help=f"Path to config file (default: {CONFIG_FILE})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    discord_required = args.mode == "full"

    try:
        host, port, username, password, key_path, remote_dir, remote_tar, local_tar, guild_id, token, config_category = load_config(
            args.config, discord_required=discord_required
        )
        category = config_category
    except Exception as e:
        print(f"[error] config error: {e}")
        sys.exit(1)


    ssh_client = None
    try:
        ssh_client = create_ssh_client(host, port, username, password, key_path)
        create_remote_tar(ssh_client, remote_dir, remote_tar)
        download_remote_file(ssh_client, remote_tar, local_tar)
        delete_remote_file(ssh_client, remote_tar)
    except paramiko.AuthenticationException:
        print("[error] ssh authentication failed (check config.ini / env vars).")
        return
    except paramiko.SSHException as e:
        print(f"[error] ssh connection problem: {e}")
        return
    except Exception as e:
        print(f"[error] unexpected error during SSH/tar/scp: {e}")
        return
    finally:
        if ssh_client is not None:
            ssh_client.close()
            print("[*] ssh connection closed.")

    if args.mode == "tar":
        print("[+] tar mode complete. archive saved to:", args.config)
        return

    # Discord flow
    try:
        print("[*] starting discord bot flow")
        asyncio.run(run_full_flow(local_tar, guild_id, token, existing_category=category))
        print("[+] discord bot flow completed.")
    except Exception as e:
        print(f"[error] discord bot flow failed: {e}")


if __name__ == "__main__":
    main()