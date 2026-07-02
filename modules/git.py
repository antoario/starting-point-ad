import os
import tarfile
import subprocess
import asyncio
from modules.base import BaseTask

class TarExtractorTask(BaseTask):
    """Task to extract a local tar archive to a destination directory."""

    def __init__(self, local_tar: str, dest_dir: str):
        self.local_tar = local_tar
        self.dest_dir = dest_dir

    async def run(self) -> None:
        def _run():
            print(f"[*] extracting '{self.local_tar}' to '{self.dest_dir}'...")
            os.makedirs(self.dest_dir, exist_ok=True)
            with tarfile.open(self.local_tar, "r:gz") as tf:
                try:
                    tf.extractall(self.dest_dir, filter='data')
                except TypeError:
                    tf.extractall(self.dest_dir)
            print("[+] archive extracted.")

        await asyncio.to_thread(_run)

class GitInitializerTask(BaseTask):
    """Task to initialize a Git repository and commit an initial snapshot."""

    def __init__(self, git_dir: str):
        self.git_dir = git_dir

    async def run(self) -> None:
        def _run():
            print(f"[*] initializing git repo in '{self.git_dir}'...")
            subprocess.run(["git", "init"], cwd=self.git_dir, check=True, capture_output=True)
            subprocess.run(["git", "add", "-A"], cwd=self.git_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial snapshot"], cwd=self.git_dir, check=True, capture_output=True)
            print("[+] git repo initialized and initial snapshot committed.")

        await asyncio.to_thread(_run)
