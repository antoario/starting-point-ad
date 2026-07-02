import os
import shlex
import paramiko
from scp import SCPClient

class SSHClientWrapper:
    """Wrapper around paramiko.SSHClient and scp.SCPClient for reusable SSH operations."""

    def __init__(self, host: str, port: int, username: str, password: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        """Establishes the SSH connection."""
        print(f"[*] connecting to {self.username}@{self.host}:{self.port}")
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        self.client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        print("[+] ssh connection established.")

    def execute_command(self, command: str) -> tuple[str, str]:
        """Runs a command on the remote host via login bash shell."""
        if not self.client:
            raise RuntimeError("SSH client is not connected.")
        
        wrapped_cmd = f"bash -lc {shlex.quote(command)}"
        print(f"[*] running remote command: {wrapped_cmd}")
        _, stdout, stderr = self.client.exec_command(wrapped_cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        return out, err

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Downloads a remote file locally using SCPClient."""
        if not self.client:
            raise RuntimeError("SSH client is not connected.")
        
        print(f"[*] downloading remote file '{remote_path}' to '{local_path}'")
        with SCPClient(self.client.get_transport()) as scp:
            scp.get(remote_path, local_path=local_path)
        print("[+] download completed.")

    def close(self) -> None:
        """Closes the SSH client connection."""
        if self.client:
            self.client.close()
            self.client = None
            print("[*] ssh connection closed.")
