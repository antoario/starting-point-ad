import os
import asyncio
import re
import discord
from modules.base import BaseTask
from modules.discord import get_directory_names, DiscordConnectionManager

MAX_FINDINGS = 50
SENSITIVE_PATTERN = re.compile(
    r'(password|passwd|pwd|secret.?key|secret|token|api.?key|private.?key|credential|key)'
    r'\s*[=:]\s*'
    r'(?:'
        r'["\'][^"\']{8,}["\']'
        r'|'
        r'[a-zA-Z0-9+/=_\-]{20,}'
    r')',
    re.IGNORECASE,
)
SKIP_EXTENSIONS = {'.pyc', '.pyo', '.class', '.o', '.so', '.a', '.bin', '.exe', '.dll'}
SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.tox', '.mypy_cache'}
EXCEPTION_LINE = re.compile(
    r'^(Traceback \(|  File "|During handling|[A-Za-z]+Error:|[A-Za-z]+Exception:|[A-Za-z]+Warning:|\s+File ".*", line \d+)'
)

class CredentialScannerTask(BaseTask):
    """Task to scan local service files for hardcoded sensitive keywords in pure Python."""

    def __init__(self, git_dir: str, tar_path: str):
        self.git_dir = git_dir
        self.tar_path = tar_path
        self.findings: list[str] = []
        self.total: int = 0

    async def run(self) -> None:
        def _run():
            dir_names = get_directory_names(self.tar_path)
            scan_dirs = [
                os.path.join(self.git_dir, d) 
                for d in dir_names 
                if os.path.isdir(os.path.join(self.git_dir, d))
            ]
            if not scan_dirs:
                return

            for root_dir in scan_dirs:
                for root, dirs, files in os.walk(root_dir):
                    # Filter out directories to skip
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                    for file in files:
                        _, ext = os.path.splitext(file)
                        if ext in SKIP_EXTENSIONS:
                            continue

                        fpath = os.path.join(root, file)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                for lineno, line in enumerate(f, 1):
                                    if EXCEPTION_LINE.match(line):
                                        continue

                                    match = SENSITIVE_PATTERN.search(line)
                                    if match:
                                        pre = line[:match.start()].rstrip()
                                        if pre.endswith(("(", ",")):
                                            continue

                                        self.total += 1
                                        if len(self.findings) < MAX_FINDINGS:
                                            # Format path with forward slashes for cross-platform consistency
                                            clean_path = fpath.replace("\\", "/")
                                            self.findings.append(f"`{clean_path}:{lineno}` {line.strip()}")
                        except Exception:
                            # Ignore read errors for unreadable or binary files
                            pass

        await asyncio.to_thread(_run)

class DiscordReportSenderTask(BaseTask):
    """Task to send formatted scanner findings to the Discord general channel."""

    def __init__(self, discord_manager: DiscordConnectionManager, findings: list[str], total: int):
        self.discord_manager = discord_manager
        self.findings = findings
        self.total = total

    async def _send_text(self, channel: discord.TextChannel, content: str) -> None:
        try:
            await asyncio.wait_for(channel.send(content), timeout=30.0)
        except asyncio.TimeoutError:
            print("[warning] channel.send timed out, skipping chunk.")
        except Exception as e:
            print(f"[warning] channel.send failed: {e}")

    async def run(self) -> None:
        channel = self.discord_manager.general_channel
        if channel is None:
            print("[warning] no 'general' channel found — scan results will not be posted.")
            return

        print("[*] reporting scan results to Discord...")
        if not self.findings:
            await self._send_text(channel, "🔍 no sensitive keywords found in archive.")
            return

        chunk = "🔍 **sensitive keywords found**:\n"
        for entry in self.findings:
            line = entry + "\n"
            if len(chunk) + len(line) > 1900:
                await self._send_text(channel, chunk)
                chunk = line
            else:
                chunk += line
        if chunk:
            await self._send_text(channel, chunk)
