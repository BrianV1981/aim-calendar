#!/usr/bin/env python3
"""
Unit and Integration Tests for core/sync_daemon.sh
Tests CLI arguments, dry-run mode, lockfile handling, rclone copy logic, and pipeline triggers.
"""

import os
import subprocess
import tempfile
import unittest
import shutil

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNC_SCRIPT = os.path.join(REPO_ROOT, "core", "sync_daemon.sh")


class TestSyncDaemon(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aim_test_sync_")
        self.mock_remote_dir = os.path.join(self.temp_dir, "mock_remote")
        self.mock_sms_remote = os.path.join(self.mock_remote_dir, "sms")
        self.mock_audio_remote = os.path.join(self.mock_remote_dir, "audio")
        self.mock_local_dir = os.path.join(self.temp_dir, "mock_local")
        self.mock_sms_local = os.path.join(self.mock_local_dir, "sms_raw")
        self.mock_audio_local = os.path.join(self.mock_local_dir, "TalkerACR")
        self.mock_log = os.path.join(self.temp_dir, "sync.log")
        self.mock_lock = os.path.join(self.temp_dir, "sync.lock")

        os.makedirs(self.mock_sms_remote, exist_ok=True)
        os.makedirs(self.mock_audio_remote, exist_ok=True)
        os.makedirs(self.mock_sms_local, exist_ok=True)
        os.makedirs(self.mock_audio_local, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_help_flag(self):
        """--help flag returns exit code 0 and prints usage."""
        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--help"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)
        self.assertIn("--once", result.stdout)
        self.assertIn("--dry-run", result.stdout)

    def test_dry_run_flag(self):
        """--dry-run flag does not modify local files."""
        # Create a file in remote
        test_file = os.path.join(self.mock_sms_remote, "test_call.xml")
        with open(test_file, "w") as f:
            f.write("<xml>test</xml>")

        env = os.environ.copy()
        env["GDRIVE_SMS_PATH"] = self.mock_sms_remote
        env["GDRIVE_AUDIO_PATH"] = self.mock_audio_remote
        env["LOCAL_SMS_DIR"] = self.mock_sms_local
        env["LOCAL_AUDIO_DIR"] = self.mock_audio_local
        env["LOG_FILE"] = self.mock_log
        env["LOCK_FILE"] = self.mock_lock
        env["USE_LOCAL_MOCK"] = "1"

        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--once", "--dry-run"],
            capture_output=True,
            text=True,
            env=env
        )
        self.assertEqual(result.returncode, 0)
        # Should NOT copy to local
        dest_file = os.path.join(self.mock_sms_local, "test_call.xml")
        self.assertFalse(os.path.exists(dest_file), "Dry run must not copy files to destination.")

    def test_sync_copies_new_files(self):
        """Sync copies new files from remote to local directories."""
        test_xml = os.path.join(self.mock_sms_remote, "sms-sample.xml")
        with open(test_xml, "w") as f:
            f.write("<smses><sms body='Hello' /></smses>")

        test_amr = os.path.join(self.mock_audio_remote, "sample.amr")
        with open(test_amr, "wb") as f:
            f.write(b"#!AMR\nfake_amr_data")

        env = os.environ.copy()
        env["GDRIVE_SMS_PATH"] = self.mock_sms_remote
        env["GDRIVE_AUDIO_PATH"] = self.mock_audio_remote
        env["LOCAL_SMS_DIR"] = self.mock_sms_local
        env["LOCAL_AUDIO_DIR"] = self.mock_audio_local
        env["LOG_FILE"] = self.mock_log
        env["LOCK_FILE"] = self.mock_lock
        env["USE_LOCAL_MOCK"] = "1"

        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--once", "--no-pipeline"],
            capture_output=True,
            text=True,
            env=env
        )
        self.assertEqual(result.returncode, 0, f"Sync script failed: {result.stderr}")

        dest_xml = os.path.join(self.mock_sms_local, "sms-sample.xml")
        dest_amr = os.path.join(self.mock_audio_local, "sample.amr")
        self.assertTrue(os.path.exists(dest_xml), "SMS XML was not copied.")
        self.assertTrue(os.path.exists(dest_amr), "Audio AMR was not copied.")

    def test_lockfile_prevents_overlap(self):
        """If a lockfile is already held, second invocation exits cleanly."""
        # Create existing lock with current PID
        with open(self.mock_lock, "w") as f:
            f.write(str(os.getpid()))

        env = os.environ.copy()
        env["LOCK_FILE"] = self.mock_lock
        env["LOG_FILE"] = self.mock_log

        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--once", "--no-pipeline"],
            capture_output=True,
            text=True,
            env=env
        )
        # Should gracefully detect existing running process and exit without error
        self.assertEqual(result.returncode, 0)
        output = (result.stdout + result.stderr).lower()
        self.assertTrue("lock" in output or "already running" in output, f"Unexpected output: {output}")

    def test_trigger_pipeline_when_new_files(self):
        """When new files are detected, downstream trigger hook is called."""
        test_xml = os.path.join(self.mock_sms_remote, "sms-new.xml")
        with open(test_xml, "w") as f:
            f.write("<smses></smses>")

        # Create a mock trigger script that records when it was run
        trigger_marker = os.path.join(self.temp_dir, "trigger_marker.txt")
        mock_pipeline_script = os.path.join(self.temp_dir, "mock_ingest.py")
        with open(mock_pipeline_script, "w") as f:
            f.write(f"with open('{trigger_marker}', 'w') as f: f.write('TRIGGERED')\n")

        env = os.environ.copy()
        env["GDRIVE_SMS_PATH"] = self.mock_sms_remote
        env["GDRIVE_AUDIO_PATH"] = self.mock_audio_remote
        env["LOCAL_SMS_DIR"] = self.mock_sms_local
        env["LOCAL_AUDIO_DIR"] = self.mock_audio_local
        env["LOG_FILE"] = self.mock_log
        env["LOCK_FILE"] = self.mock_lock
        env["USE_LOCAL_MOCK"] = "1"
        env["OVERRIDE_SMS_INGEST_SCRIPT"] = mock_pipeline_script

        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--once"],
            capture_output=True,
            text=True,
            env=env
        )
        self.assertEqual(result.returncode, 0, f"Sync script failed: {result.stderr}")
        self.assertTrue(os.path.exists(trigger_marker), "Downstream pipeline script was not triggered.")

    def test_status_flag(self):
        """--status outputs status report cleanly."""
        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--status"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("A.I.M. Sync Daemon Status", result.stdout)

    def test_install_cron_flag(self):
        """--install-cron outputs crontab recommendation."""
        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--install-cron"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("crontab", result.stdout)
        self.assertIn("sync_daemon.sh --once", result.stdout)

    def test_zip_archive_extraction(self):
        """When a .zip file is present in SMS sync, it is extracted."""
        import zipfile
        zip_path = os.path.join(self.mock_sms_remote, "sms_backup_test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("extracted_test.xml", "<xml>from zip</xml>")

        env = os.environ.copy()
        env["GDRIVE_SMS_PATH"] = self.mock_sms_remote
        env["GDRIVE_AUDIO_PATH"] = self.mock_audio_remote
        env["LOCAL_SMS_DIR"] = self.mock_sms_local
        env["LOCAL_AUDIO_DIR"] = self.mock_audio_local
        env["LOG_FILE"] = self.mock_log
        env["LOCK_FILE"] = self.mock_lock
        env["USE_LOCAL_MOCK"] = "1"

        result = subprocess.run(
            ["bash", SYNC_SCRIPT, "--once", "--no-pipeline"],
            capture_output=True,
            text=True,
            env=env
        )
        self.assertEqual(result.returncode, 0, f"Sync script failed: {result.stderr}")
        extracted_file = os.path.join(self.mock_sms_local, "extracted_test.xml")
        self.assertTrue(os.path.exists(extracted_file), "Zip archive was not unpacked in SMS folder.")


if __name__ == "__main__":
    unittest.main()
