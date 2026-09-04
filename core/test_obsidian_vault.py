import unittest
import os
import tempfile
import shutil
import json
from core.obsidian_vault import (
    setup_vault,
    update_daily_note_frontmatter,
    migrate_daily_notes_tags,
    parse_frontmatter_tags,
    DEFAULT_TAGS
)


class TestObsidianVault(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aim_test_obsidian_")
        self.notes_dir = os.path.join(self.test_dir, "daily_notes")
        os.makedirs(self.notes_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_setup_vault_creates_core_files(self):
        """Test setup_vault initializes the complete .obsidian directory structure."""
        created = setup_vault(
            vault_dir=self.test_dir,
            daily_notes_folder="daily_notes",
            media_folder="media",
            install_plugin=True
        )

        obsidian_dir = os.path.join(self.test_dir, ".obsidian")
        self.assertTrue(os.path.isdir(obsidian_dir))

        # 1. app.json
        app_json = os.path.join(obsidian_dir, "app.json")
        self.assertTrue(os.path.exists(app_json))
        with open(app_json, "r", encoding="utf-8") as f:
            app_data = json.load(f)
        self.assertEqual(app_data.get("attachmentFolderPath"), "media")
        self.assertEqual(app_data.get("newFileFolderPath"), "daily_notes")
        self.assertTrue(app_data.get("useMarkdownLinks"))

        # 2. core-plugins.json
        core_plugins_json = os.path.join(obsidian_dir, "core-plugins.json")
        self.assertTrue(os.path.exists(core_plugins_json))
        with open(core_plugins_json, "r", encoding="utf-8") as f:
            core_plugins = json.load(f)
        self.assertTrue(core_plugins.get("daily-notes"))
        self.assertTrue(core_plugins.get("tag-pane"))
        self.assertTrue(core_plugins.get("graph"))

        # 3. daily-notes.json
        daily_notes_json = os.path.join(obsidian_dir, "daily-notes.json")
        self.assertTrue(os.path.exists(daily_notes_json))
        with open(daily_notes_json, "r", encoding="utf-8") as f:
            daily_conf = json.load(f)
        self.assertEqual(daily_conf.get("format"), "YYYY-MM-DD")
        self.assertEqual(daily_conf.get("folder"), "daily_notes")

        # 4. community-plugins.json
        comm_plugins_json = os.path.join(obsidian_dir, "community-plugins.json")
        self.assertTrue(os.path.exists(comm_plugins_json))
        with open(comm_plugins_json, "r", encoding="utf-8") as f:
            comm_list = json.load(f)
        self.assertIn("calendar", comm_list)

        # 5. Calendar plugin files
        plugin_dir = os.path.join(obsidian_dir, "plugins", "calendar")
        self.assertTrue(os.path.isdir(plugin_dir))
        self.assertTrue(os.path.exists(os.path.join(plugin_dir, "manifest.json")))
        self.assertTrue(os.path.exists(os.path.join(plugin_dir, "data.json")))
        self.assertTrue(os.path.exists(os.path.join(plugin_dir, "main.js")))

    def test_update_daily_note_frontmatter_adds_tags(self):
        """Test adding tags to an existing daily note with basic frontmatter."""
        note_path = os.path.join(self.notes_dir, "2026-08-30.md")
        content = "---\ndate: 2026-08-30\ntype: daily_exocortex\n---\n# Daily Log: 2026-08-30\n\n- **[10:00 AM] Sent Text** (+1234): \"Hello\""
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)

        modified = update_daily_note_frontmatter(note_path)
        self.assertTrue(modified)

        with open(note_path, "r", encoding="utf-8") as f:
            updated = f.read()

        for tag in DEFAULT_TAGS:
            self.assertIn(f"- {tag}", updated)
        self.assertIn("date: 2026-08-30", updated)
        self.assertIn("type: daily_exocortex", updated)
        self.assertIn("# Daily Log: 2026-08-30", updated)
        self.assertIn("- **[10:00 AM] Sent Text**", updated)

    def test_update_daily_note_frontmatter_merges_existing_tags(self):
        """Test merging calendar tags with custom pre-existing tags."""
        note_path = os.path.join(self.notes_dir, "2026-08-31.md")
        content = "---\ndate: 2026-08-31\ntags: [client-call, urgent]\n---\n# Daily Log: 2026-08-31\n\n- **[11:00 AM] Call**"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)

        modified = update_daily_note_frontmatter(note_path)
        self.assertTrue(modified)

        with open(note_path, "r", encoding="utf-8") as f:
            updated = f.read()

        self.assertIn("- client-call", updated)
        self.assertIn("- urgent", updated)
        self.assertIn("- daily-note", updated)
        self.assertIn("- calendar", updated)

    def test_update_daily_note_without_frontmatter(self):
        """Test creating frontmatter when note has none."""
        note_path = os.path.join(self.notes_dir, "2026-09-01.md")
        content = "# Raw Daily Note\n\n- Some bullet text"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)

        modified = update_daily_note_frontmatter(note_path)
        self.assertTrue(modified)

        with open(note_path, "r", encoding="utf-8") as f:
            updated = f.read()

        self.assertIn("date: 2026-09-01", updated)
        self.assertIn("tags:", updated)
        self.assertIn("- daily-note", updated)
        self.assertIn("# Raw Daily Note", updated)

    def test_idempotency(self):
        """Test that running update twice does not re-modify already updated notes."""
        note_path = os.path.join(self.notes_dir, "2026-09-02.md")
        content = "---\ndate: 2026-09-02\ntype: daily_exocortex\n---\n# Daily Log"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)

        # First run
        mod1 = update_daily_note_frontmatter(note_path)
        self.assertTrue(mod1)

        with open(note_path, "r", encoding="utf-8") as f:
            first_pass = f.read()

        # Second run
        mod2 = update_daily_note_frontmatter(note_path)
        self.assertFalse(mod2)

        with open(note_path, "r", encoding="utf-8") as f:
            second_pass = f.read()

        self.assertEqual(first_pass, second_pass)

    def test_migrate_daily_notes_batch(self):
        """Test batch migration of multiple daily notes."""
        for d in ["2026-08-01", "2026-08-02", "2026-08-03"]:
            p = os.path.join(self.notes_dir, f"{d}.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"---\ndate: {d}\n---\n# Log")

        updated_count, total_count = migrate_daily_notes_tags(self.notes_dir)
        self.assertEqual(total_count, 3)
        self.assertEqual(updated_count, 3)

        # Second migration should update 0 files
        updated_count2, total_count2 = migrate_daily_notes_tags(self.notes_dir)
        self.assertEqual(updated_count2, 0)
        self.assertEqual(total_count2, 3)


if __name__ == "__main__":
    unittest.main()
