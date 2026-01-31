import configparser
import paramiko
from scp import SCPClient
import sys
import asyncio
import os
import zipfile
import subprocess
import shutil

from bot import run_full_flow

CONFIG_FILE = "config.ini"

def load_config(path: str):
    config = configparser.ConfigParser()
    read_files = config.read(path, encoding="utf-8")

    if not read_files:
        raise FileNotFoundError(
            f"Config file '{path}' not found. "
            f"Make sure you copied 'config.ini.example' to '{path}' and configured it."
        )

    # SSH data
    if "ssh" not in config:
        raise ValueError(f"Section [ssh] missing in '{path}'")

    ssh_conf = config["ssh"]

    host = ssh_conf.get("host", "").strip()
    username = ssh_conf.get("username", "").strip()
    password = ssh_conf.get("password", "").strip()
    port_str = ssh_conf.get("port", "22").strip()

    if not host or not username or not password:
        raise ValueError(
            "Missing one or more required fields in the [ssh] section: "
            "host, username, password."
        )

    try:
        port = int(port_str)
    except ValueError:
        raise ValueError("Field 'port' in the config file must be an integer.")

    if "paths" not in config:
        raise ValueError(f"Section [paths] missing in '{path}'")

    paths_conf = config["paths"]

    remote_dir = paths_conf.get("remote_dir", "~").strip()
    remote_zip = paths_conf.get("remote_zip", "~/backup.zip").strip()
    local_zip = paths_conf.get("local_zip", "backup.zip").strip()

    # Discord data
    if "discord" not in config:
        raise ValueError(f"Section [discord] missing in '{path}'")

    discord_conf = config["discord"]
    guild_id_str = discord_conf.get("guild_id", "").strip()
    if not guild_id_str:
        raise ValueError("Field 'guild_id' is required in [discord] section.")

    try:
        guild_id = int(guild_id_str)
    except ValueError:
        raise ValueError("Field 'guild_id' in the config file must be an integer.")

    #  Github data
    if "git" not in config:
        raise ValueError(f"Section [git] missing in '{path}'")

    git_conf = config["git"]
    repo_name = git_conf.get("repo_name", "").strip()
    git_commit_message = git_conf.get("commit_message", "Initial AD snapshot").strip()
    visibility = git_conf.get("visibility", "private").strip().lower()
    collaborators_str = git_conf.get("collaborators", "").strip()

    if not repo_name:
        raise ValueError("Field 'repo_name' is required in [git] section.")

    if visibility not in ("private", "public"):
        raise ValueError("Field 'visibility' in [git] must be 'private' or 'public'.")

    collaborators = []
    if collaborators_str:
        collaborators = [c.strip() for c in collaborators_str.split(",") if c.strip()]

    return (
        host,
        port,
        username,
        password,
        remote_dir,
        remote_zip,
        local_zip,
        guild_id,
        repo_name,
        git_commit_message,
        visibility,
        collaborators,
    )


def create_ssh_client(host: str, port: int, username: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"[*] Connecting to {username}@{host}:{port}...")
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    print("[+] SSH connection established.")
    return client


def run_remote_command(ssh_client: paramiko.SSHClient, command: str):
    wrapped_cmd = f"bash -lc '{command}'"
    print(f"[*] Running remote command: {wrapped_cmd}...")
    stdin, stdout, stderr = ssh_client.exec_command(wrapped_cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err


def create_remote_zip(ssh_client: paramiko.SSHClient, remote_dir: str, remote_zip: str):
    cmd = f"cd {remote_dir} && zip -r {remote_zip} ."
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        raise RuntimeError(f"Error creating remote zip: {err}")
    print("[+] Remote zip created.")


def download_remote_file(ssh_client: paramiko.SSHClient, remote_path: str, local_path: str):
    print(f"[*] Downloading remote file '{remote_path}' to '{local_path}'...")
    with SCPClient(ssh_client.get_transport()) as scp:
        scp.get(remote_path, local_path=local_path)
    print("[+] Download completed.")


def delete_remote_file(ssh_client: paramiko.SSHClient, remote_path: str):
    cmd = f"rm -f {remote_path}"
    out, err = run_remote_command(ssh_client, cmd)
    if err:
        raise RuntimeError(f"Error deleting remote file: {err}")
    print("[+] Remote zip deleted.")


def ensure_local_repo_dir(repo_name: str) -> str:
    base_dir = os.getcwd()
    repo_dir = os.path.join(base_dir, repo_name)
    os.makedirs(repo_dir, exist_ok=True)
    return repo_dir


def extract_zip_into_dir(zip_path: str, target_dir: str):
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Local zip file '{zip_path}' not found.")

    print(f"[*] Extracting '{zip_path}' into '{target_dir}'...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    print("[+] Extraction completed.")


def run_cmd(cmd, cwd=None):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout.strip()


def ensure_gh_available():
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI 'gh' is not installed or not found in PATH. "
                           "Install it from https://cli.github.com/ and run 'gh auth login'.")



def ensure_git_repo_initialized(repo_dir: str):
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        print("[*] Initializing local git repo...")
        run_cmd(["git", "init"], cwd=repo_dir)
        print("[+] Local git repo initialized.")
    else:
        print("[*] Local git repo already initialized.")


def ensure_github_repo_exists(repo_dir: str, repo_name: str, visibility: str):
    ensure_gh_available()

    exists = True
    try:
        run_cmd(["gh", "repo", "view", repo_name], cwd=repo_dir)
        print(f"[*] GitHub repo '{repo_name}' already exists.")
    except RuntimeError:
        exists = False

    if not exists:
        vis_flag = "--private" if visibility == "private" else "--public"
        print(f"[*] Creating GitHub repo '{repo_name}' ({visibility})...")
        run_cmd(
            ["gh", "repo", "create", repo_name, vis_flag, "--source=."],
            cwd=repo_dir,
        )
        print(f"[+] GitHub repo '{repo_name}' created on GitHub.")


def git_commit_and_push(repo_dir: str, repo_name: str, commit_message: str):
    print(f"[*] Committing and pushing changes...")

    if not shutil.which("git"):
        raise RuntimeError("Git is not installed or not found in PATH.")

    run_cmd(["git", "add", "."], cwd=repo_dir)

    status = run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)
    if not status:
        print("[*] No changes to commit in git repo. Skipping push.")
        return

    run_cmd(["git", "commit", "-m", commit_message], cwd=repo_dir)
    print("[+] Git commit created.")

    print("[*] Ensuring 'origin' remote is set correctly ...")
    remotes = run_cmd(["git", "remote"], cwd=repo_dir).splitlines()
    if "origin" not in remotes:
        if "/" in repo_name:
            remote_url = f"git@github.com:{repo_name}.git"
        else:
            current_user = run_cmd(["gh", "api", "user", "--jq", ".login"], cwd=repo_dir)
            remote_url = f"git@github.com:{current_user}/{repo_name}.git"

        run_cmd(["git", "remote", "add", "origin", remote_url], cwd=repo_dir)
        print(f"[*] Added origin remote: {remote_url}")
    else:
        print("[*] Remote 'origin' already set.")

    current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    print(f"[*] Pushing branch '{current_branch}' to origin ...")
    run_cmd(["git", "push", "-u", "origin", current_branch], cwd=repo_dir)
    print(f"[+] Changes pushed to 'origin/{current_branch}'.")


#  NOT TESTED!!!
def invite_collaborators(repo_name: str, collaborators: list[str], repo_dir: str):
    if not collaborators:
        return

    ensure_gh_available()

    if "/" in repo_name:
        owner, name = repo_name.split("/", 1)
    else:
        owner = run_cmd(["gh", "api", "user", "--jq", ".login"], cwd=repo_dir)
        name = repo_name

    full_name = f"{owner}/{name}"
    print(f"[*] Inviting collaborators to GitHub repo '{full_name}' ...")

    for user in collaborators:
        try:
            run_cmd(
                [
                    "gh", "api",
                    f"/repos/{owner}/{name}/collaborators/{user}",
                    "--method", "PUT",
                    "-f", "permission=push",
                ],
                cwd=repo_dir,
            )
            print(f"[+] Collaborator '{user}' invited.")
        except RuntimeError as e:
            print(f"[ERROR] Failed to add collaborator '{user}': {e}")
    print("----------")


def main():
    try:
        (
            host,
            port,
            username,
            password,
            remote_dir,
            remote_zip,
            local_zip,
            guild_id,
            repo_name,
            git_commit_message,
            visibility,
            collaborators,
        ) = load_config(CONFIG_FILE)
    except Exception as e:
        print(f"[CONFIG ERROR] {e}")
        sys.exit(1)

    # SSH flow
    ssh_client = None
    try:
        ssh_client = create_ssh_client(host, port, username, password)

        create_remote_zip(ssh_client, remote_dir, remote_zip)
        download_remote_file(ssh_client, remote_zip, local_zip)
        delete_remote_file(ssh_client, remote_zip)

    except paramiko.AuthenticationException:
        print("[ERROR] SSH authentication failed (check username/password in config.ini).")
        return
    except paramiko.SSHException as e:
        print(f"[ERROR] SSH connection problem: {e}")
        return
    except Exception as e:
        print(f"[ERROR] Unexpected error during SSH/zip/scp: {e}")
        return
    finally:
        if ssh_client is not None:
            ssh_client.close()
            print("[*] SSH connection closed.")
            print("----------")

    # Github flow
    try:
        repo_dir = ensure_local_repo_dir(repo_name)
        extract_zip_into_dir(local_zip, repo_dir)

        ensure_git_repo_initialized(repo_dir)
        ensure_github_repo_exists(repo_dir, repo_name, visibility)
        git_commit_and_push(repo_dir, repo_name, git_commit_message)
        invite_collaborators(repo_name, collaborators, repo_dir)

    except Exception as e:
        print(f"[ERROR] GitHub repo / git flow failed: {e}")

    # Discord flow
    try:
        print("[*] Starting Discord bot flow...")
        asyncio.run(run_full_flow(local_zip, guild_id))
        print("[+] Discord bot flow completed.")
    except Exception as e:
        print(f"[ERROR] Discord bot flow failed: {e}")


if __name__ == "__main__":
    main()