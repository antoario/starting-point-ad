import configparser
import paramiko
from scp import SCPClient
import sys
import asyncio
import os
import tarfile
import subprocess
from bot import run_full_flow

CONFIG_FILE = "config.ini"

def load_config(path: str):
    config = configparser.ConfigParser()
    read_files = config.read(path, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(f"config file '{path}' not found.")
    if "ssh" not in config:
        raise ValueError(f"section [ssh] missing in '{path}'.")
    if "paths" not in config:
        raise ValueError(f"section [paths] missing in '{path}'.")
    if "discord" not in config:
        raise ValueError(f"section [discord] missing in '{path}'.")

    ssh_conf = config["ssh"]
    host = ssh_conf.get("host", "").strip()
    username = ssh_conf.get("username", "").strip()
    password = ssh_conf.get("password", "").strip()
    port_str = ssh_conf.get("port", "22").strip()

    if not host or not username or not password:
        raise ValueError("missing one or more required fields in the [ssh] section: host, username or password.")
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError("field [port] in the config file must be an integer.")

    paths_conf = config["paths"]
    remote_dir = paths_conf.get("remote_dir", "~").strip()
    remote_tar = paths_conf.get("remote_tar", "~/backup.tar.gz").strip()
    local_tar = paths_conf.get("local_tar", "backup.tar.gz").strip()

    discord_conf = config["discord"]
    guild_id_str = discord_conf.get("guild_id", "").strip()
    if not guild_id_str:
        raise ValueError("field [guild_id] is required in [discord] section.")
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        raise ValueError("field [guild_id] in the config file must be an integer.")

    return (host, port, username, password, remote_dir, remote_tar, local_tar, guild_id)


def create_ssh_client(host: str, port: int, username: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[*] connecting to {username}@{host}:{port}...")
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    print("[+] ssh connection established.")
    return client


def run_remote_command(ssh_client: paramiko.SSHClient, command: str):
    wrapped_cmd = f"bash -lc '{command}'"
    print(f"[*] running remote command: {wrapped_cmd}...")
    _, stdout, stderr = ssh_client.exec_command(wrapped_cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err


def create_remote_tar(ssh_client: paramiko.SSHClient, remote_dir: str, remote_tar: str):
    tar_filename = os.path.basename(remote_tar)
    cmd = f"cd {remote_dir} && tar -czf {remote_tar} --exclude=./{tar_filename} ."
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        raise RuntimeError(f"error creating remote tar: {err}")
    print("[+] remote tar created.")


def download_remote_file(ssh_client: paramiko.SSHClient, remote_path: str, local_path: str):
    print(f"[*] downloading remote file '{remote_path}' to '{local_path}'...")
    with SCPClient(ssh_client.get_transport()) as scp:
        scp.get(remote_path, local_path=local_path)
    print("[+] download completed.")


def delete_remote_file(ssh_client: paramiko.SSHClient, remote_path: str):
    cmd = f"rm -f {remote_path}"
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        raise RuntimeError(f"error deleting remote file: {err}")
    print("[+] remote tar deleted.")


def extract_tar_into_dir(tar_path: str, target_dir: str):
    if not os.path.exists(tar_path):
        raise FileNotFoundError(f"local tar file '{tar_path}' not found.")
    print(f"[*] extracting '{tar_path}' into '{target_dir}'...")
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(target_dir)
    print("[+] extraction completed.")


def run_cmd(cmd, cwd=None):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result.stdout.strip()


def main():
    try:
        (
            host,
            port,
            username,
            password,
            remote_dir,
            remote_tar,
            local_tar,
            guild_id,
        ) = load_config(CONFIG_FILE)
    except Exception as e:
        print(f"config error: {e}")
        sys.exit(1)

    # ssh flow
    ssh_client = None
    try:
        ssh_client = create_ssh_client(host, port, username, password)
        create_remote_tar(ssh_client, remote_dir, remote_tar)
        download_remote_file(ssh_client, remote_tar, local_tar)
        delete_remote_file(ssh_client, remote_tar)
    except paramiko.AuthenticationException:
        print("[error] ssh authentication failed (check username/password in config.ini).")
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

    # discord flow
    try:
        print("[*] starting Discord bot flow...")
        asyncio.run(run_full_flow(local_tar, guild_id))
        print("[+] discord bot flow completed.")
    except Exception as e:
        print(f"[error] discord bot flow failed: {e}")


if __name__ == "__main__":
    main()