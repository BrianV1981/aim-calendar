# Community & Open Source Migration

As of **September 10, 2026**, the `aim-calendar` repository has been fully decoupled from local environment specifics to enable seamless sharing and community collaboration.

## Core Decoupling Operations
1. **Local Path Standardization:** The root repository folder has been formally unified as `aim-calendar` across both local checkouts and upstream GitHub tracking, eliminating prior discrepancies (e.g., `aim-talkeracr`).
2. **Environment Isolation:** The sovereign `joshua_os` agent framework directory has been added to `.gitignore` to prevent operational leakages.
3. **Dynamic Integrations:** All hardcoded system paths (e.g., `/home/kingb`) have been stripped from the `core/` pipeline logic.

## Environment Variable Configuration (`AIM_MEMORY_PATH`)

For developers leveraging the broader `aim-memory` frameworks, the ingestion pipelines (`core/ingest_to_lancedb.py`, `core/build_cartridge.py`, and `core/test_retrieval.py`) now dynamically resolve the upstream dependencies.

By default, the pipeline gracefully attempts to resolve the memory module via `../aim-memory`. However, you can explicitly define this via environment variables:

```bash
export AIM_MEMORY_PATH="/custom/path/to/aim-memory"
```

This ensures that the repository remains 100% agnostic to the user's specific OS and file system structure.
