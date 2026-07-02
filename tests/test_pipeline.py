import os
import unittest
import tempfile
import shutil
import tarfile
import asyncio
from unittest.mock import MagicMock, patch

# Adjust import path
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import load_config
from ssh_client import SSHClientWrapper
from modules.base import BaseTask
from modules.git import TarExtractorTask
from modules.scan import CredentialScannerTask


class TestPipelineModular(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_config_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_config(os.path.join(self.test_dir, "nonexistent.ini"))

    def test_load_config_valid(self):
        config_path = os.path.join(self.test_dir, "test_config.ini")
        with open(config_path, "w") as f:
            f.write("""[ssh]
host=127.0.0.1
port=2222
username=testuser
remote_dir=/home/testuser
remote_tar=/home/testuser/backup.tar.gz

[git]
local_tar=test_backup.tar.gz
git_dir=test_ad

[discord]
guild_id=1234567890
category=TestCategory
""")

        # Set env variables
        os.environ["AD_SSH_PASSWD"] = "secret_ssh"
        os.environ["AD_DS_TOKEN"] = "secret_token"

        host, port, username, password, remote_dir, remote_tar, local_tar, git_dir, guild_id, token, category = load_config(config_path)

        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 2222)
        self.assertEqual(username, "testuser")
        self.assertEqual(password, "secret_ssh")
        self.assertEqual(remote_dir, "/home/testuser")
        self.assertEqual(remote_tar, "/home/testuser/backup.tar.gz")
        self.assertEqual(local_tar, "test_backup.tar.gz")
        self.assertEqual(git_dir, "test_ad")
        self.assertEqual(guild_id, 1234567890)
        self.assertEqual(token, "secret_token")
        self.assertEqual(category, "TestCategory")

    def test_ssh_client_wrapper_init(self):
        client = SSHClientWrapper("localhost", 22, "root", "password")
        self.assertEqual(client.host, "localhost")
        self.assertEqual(client.port, 22)
        self.assertEqual(client.username, "root")
        self.assertEqual(client.password, "password")
        self.assertIsNone(client.client)

    def test_tar_extractor_task(self):
        # Create a mock tar archive
        archive_path = os.path.join(self.test_dir, "test.tar.gz")
        extract_dest = os.path.join(self.test_dir, "extracted")
        
        dummy_dir = os.path.join(self.test_dir, "dummy_service")
        os.makedirs(dummy_dir)
        with open(os.path.join(dummy_dir, "file.txt"), "w") as f:
            f.write("hello world")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(dummy_dir, arcname="dummy_service")

        extractor = TarExtractorTask(archive_path, extract_dest)
        asyncio.run(extractor.run())

        self.assertTrue(os.path.exists(os.path.join(extract_dest, "dummy_service", "file.txt")))

    def test_credential_scanner_task(self):
        # Create a mock structure
        git_dir = os.path.join(self.test_dir, "mock_git")
        os.makedirs(os.path.join(git_dir, "service_a"))
        
        # File with credential
        with open(os.path.join(git_dir, "service_a", "config.py"), "w") as f:
            f.write("DB_PASSWORD = 'super_secret_password_123'")

        # Mock tar to get directory names
        archive_path = os.path.join(self.test_dir, "test.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tar:
            # We just need to add a folder named service_a in the tar
            dummy_folder = os.path.join(self.test_dir, "service_a")
            if not os.path.exists(dummy_folder):
                os.makedirs(dummy_folder)
            tar.add(dummy_folder, arcname="service_a")

        scanner = CredentialScannerTask(git_dir, archive_path)
        asyncio.run(scanner.run())

        self.assertGreater(scanner.total, 0)
        self.assertTrue(any("DB_PASSWORD" in f for f in scanner.findings))


if __name__ == "__main__":
    unittest.main()
