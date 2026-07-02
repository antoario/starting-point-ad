import asyncio
from modules.base import BaseTask
from ssh_client import SSHClientWrapper

class RemoteTarCreatorTask(BaseTask):
    """Task to create a tar archive of top-level service directories on the remote host."""

    def __init__(self, ssh_client: SSHClientWrapper, remote_dir: str, remote_tar: str):
        self.ssh_client = ssh_client
        self.remote_dir = remote_dir
        self.remote_tar = remote_tar

    async def run(self) -> None:
        def _run():
            cmd = (
                f"cd {self.remote_dir} && "
                f"find . -maxdepth 1 -mindepth 1 -type d ! -name '.*' -printf '%P\\n' | "
                f"tar -czf {self.remote_tar} -T -"
            )
            _, err = self.ssh_client.execute_command(cmd)
            if err and "file changed as we read it" not in err:
                raise RuntimeError(f"error creating remote tar: {err}")
            print("[+] remote tar created.")

        await asyncio.to_thread(_run)

class SCPDownloadTask(BaseTask):
    """Task to download the remote tar file using SCP."""

    def __init__(self, ssh_client: SSHClientWrapper, remote_tar: str, local_tar: str):
        self.ssh_client = ssh_client
        self.remote_tar = remote_tar
        self.local_tar = local_tar

    async def run(self) -> None:
        def _run():
            self.ssh_client.download_file(self.remote_tar, self.local_tar)

        await asyncio.to_thread(_run)

class RemoteCleanupTask(BaseTask):
    """Task to delete the remote tar file from the host."""

    def __init__(self, ssh_client: SSHClientWrapper, remote_tar: str):
        self.ssh_client = ssh_client
        self.remote_tar = remote_tar

    async def run(self) -> None:
        def _run():
            _, err = self.ssh_client.execute_command(f"rm -f {self.remote_tar}")
            if err:
                raise RuntimeError(f"error deleting remote file: {err}")
            print("[+] remote tar deleted.")

        await asyncio.to_thread(_run)
