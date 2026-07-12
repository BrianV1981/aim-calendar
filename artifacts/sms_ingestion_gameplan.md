# SMS Ingestion Gameplan (Omni-Channel Memory)

This document outlines the step-by-step architecture and task list required to safely ingest Android text messages into the A.I.M. LanceDB vector database. It is designed to mirror the `TalkerACR` audio pipeline, ensuring an unbroken, unified semantic memory.

## Phase 1: Data Extraction (Android to Cloud)
*Goal: Automate the extraction of text messages without manual intervention.*

- [ ] **Task 1.1:** Install the "SMS Backup & Restore" app on the Android device.
- [ ] **Task 1.2:** Configure the app to perform a daily scheduled backup (e.g., at 2:00 AM).
- [ ] **Task 1.3:** Authenticate the app with Google Drive and point it to a dedicated folder (e.g., `SMS_Ingest`).

## Phase 2: Secure Server Retrieval (Cloud to Linux)
*Goal: Use A.I.M.'s native `aim-google` skill to fetch the backup securely, avoiding third-party sync apps.*

- [ ] **Task 2.1:** Verify the `aim-google` CLI has correct OAuth permissions for the specific Google Drive folder.
- [ ] **Task 2.2:** Write a shell script snippet (`core/fetch_sms.sh`) that uses `aim-google drive ls --agent` to locate the newest `.xml` backup file.
- [ ] **Task 2.3:** Use `aim-google drive get <file_id> --agent` to pull the XML file into `/home/kingb/aim-talkeracr/conversations/sms_raw/`.

## Phase 3: The Parsing Engine (XML to Markdown)
*Goal: Translate the raw XML database into A.I.M.-compliant Markdown files with YAML frontmatter.*

- [ ] **Task 3.1:** Create `core/ingest_sms.py`.
- [ ] **Task 3.2:** Write logic to parse the `sms_backup.xml` schema.
- [ ] **Task 3.3:** Group messages by `contact_name` or `phone_number` and chunk them chronologically (e.g., one Markdown file per contact per week, or one continuous file).
- [ ] **Task 3.4:** Inject the strict A.I.M. YAML frontmatter:
  ```yaml
  ---
  status: golden
  platform: sms
  contact: [Contact Name]
  date: [Date String]
  ---
  ```
- [ ] **Task 3.5:** Format the dialogue natively (e.g., `[09:00 AM] Brian: Hello`).

## Phase 4: Semantic Convergence (LanceDB Ingestion)
*Goal: Embed the texts into the existing vector pool without writing new database logic.*

- [ ] **Task 4.1:** Verify that `core/ingest_to_lancedb.py` seamlessly picks up the new SMS markdown files in the `conversations/` directory.
- [ ] **Task 4.2:** Validate that the sliding-window chunker correctly processes the SMS format.
- [ ] **Task 4.3:** Run a test semantic query (`aim search`) to prove the agent can successfully recall a text message.

## Phase 5: Garbage Collection & Automation
*Goal: Prevent storage bloat and finalize the daemon.*

- [ ] **Task 5.1:** Add logic to delete the heavy `.xml` file from the Linux machine once the Markdown conversion is complete.
- [ ] **Task 5.2:** Add `core/ingest_sms.py` into the master scheduled cron daemon (`daemon_pipeline.sh`) to run alongside the audio ingestion.
