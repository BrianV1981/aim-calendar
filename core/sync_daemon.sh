#!/usr/bin/env bash
# ==============================================================================
# A.I.M. Calendar — Background Sync Daemon (Issue #4)
# Automates rclone synchronization from Google Drive into TalkerACR/ (audio)
# and conversations/sms_raw/ (texts), detecting new files and triggering
# incremental ingestion pipelines.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------------------
# 1. Environment & Default Configuration
# ------------------------------------------------------------------------------
GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive:}"
GDRIVE_AUDIO_PATH="${GDRIVE_AUDIO_PATH:-${GDRIVE_REMOTE}TalkerACR/All}"
GDRIVE_SMS_PATH="${GDRIVE_SMS_PATH:-${GDRIVE_REMOTE}sms=backup-jess}"
GDRIVE_ADFREE_SMS_PATH="${GDRIVE_ADFREE_SMS_PATH:-${GDRIVE_REMOTE}Ad-Free SMS Backups}"

LOCAL_AUDIO_DIR="${LOCAL_AUDIO_DIR:-${REPO_ROOT}/TalkerACR/All}"
LOCAL_SMS_DIR="${LOCAL_SMS_DIR:-${REPO_ROOT}/conversations/sms_raw}"
LOCAL_MEDIA_DIR="${LOCAL_MEDIA_DIR:-${REPO_ROOT}/conversations/media}"
LOG_FILE="${LOG_FILE:-${REPO_ROOT}/sync_daemon.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/aim_sync_daemon.lock}"

USE_LOCAL_MOCK="${USE_LOCAL_MOCK:-0}"
OVERRIDE_SMS_INGEST_SCRIPT="${OVERRIDE_SMS_INGEST_SCRIPT:-}"

# Python Engine Detection (supporting worktrees)
PYTHON_BIN="${REPO_ROOT}/joshua_os/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    GIT_COMMON="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
    if [ -n "$GIT_COMMON" ]; then
        MAIN_ROOT="$(dirname "$GIT_COMMON")"
        if [ -x "$MAIN_ROOT/joshua_os/venv/bin/python3" ]; then
            PYTHON_BIN="$MAIN_ROOT/joshua_os/venv/bin/python3"
        fi
    fi
fi
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(which python3 || echo "python3")"
fi

# Operational Modes
MODE="once"
DRY_RUN=0
RUN_PIPELINE=1
FORCE_PIPELINE=0
RUN_DIARIZE=0
LOOP_INTERVAL=300

# ------------------------------------------------------------------------------
# 2. Logging & Locking Functions
# ------------------------------------------------------------------------------
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" >&2
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$msg" >> "$LOG_FILE"
}

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local old_pid
        old_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            log "[WARN] Sync daemon is already running (PID: $old_pid). Exiting cleanly."
            exit 0
        else
            log "[INFO] Stale lockfile detected (PID: $old_pid). Cleaning up."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo "$$" > "$LOCK_FILE"
    trap cleanup EXIT INT TERM
}

cleanup() {
    rm -f "$LOCK_FILE"
}

# ------------------------------------------------------------------------------
# 3. Core Sync Procedures
# ------------------------------------------------------------------------------
count_files() {
    local dir="$1"
    if [ -d "$dir" ]; then
        find "$dir" -maxdepth 1 -type f | wc -l
    else
        echo 0
    fi
}

sync_source() {
    local remote="$1"
    local local_dest="$2"
    local label="$3"

    mkdir -p "$local_dest"
    local count_before
    count_before="$(count_files "$local_dest")"

    log "[SYNC] Starting sync for $label..."
    log "       Source: $remote"
    log "       Dest:   $local_dest"

    if [ "$USE_LOCAL_MOCK" = "1" ]; then
        if [ "$DRY_RUN" = "1" ]; then
            log "[DRY-RUN] Would copy files from $remote to $local_dest"
            echo 0
            return 0
        fi
        if [ -d "$remote" ]; then
            cp -n "$remote"/* "$local_dest"/ 2>/dev/null || true
        fi
    else
        local rclone_args=("--update" "--transfers=4")
        if [ "$DRY_RUN" = "1" ]; then
            rclone_args+=("--dry-run")
        fi

        # Test if remote directory exists / is accessible
        if ! rclone lsf "$remote" --max-depth 1 >/dev/null 2>&1; then
            log "[WARN] Remote path $remote unreachable or does not exist. Skipping."
            echo 0
            return 0
        fi

        log "[RCLONE] Executing rclone copy $remote -> $local_dest"
        rclone copy "$remote" "$local_dest" "${rclone_args[@]}" >> "$LOG_FILE" 2>&1 || {
            log "[ERROR] rclone copy failed for $label"
            echo 0
            return 1
        }

        if [ "$DRY_RUN" = "1" ]; then
            log "[DRY-RUN] Simulation finished for $label."
            echo 0
            return 0
        fi
    fi

    # Unpack any new zip archives in SMS folder (e.g. from Ad-Free SMS backups)
    if [ "$label" = "SMS/Texts" ] && [ "$DRY_RUN" = "0" ]; then
        for zip_file in "$local_dest"/*.zip; do
            if [ -f "$zip_file" ]; then
                local marker="${zip_file}.extracted"
                if [ ! -f "$marker" ]; then
                    log "[UNZIP] Extracting new archive: $(basename "$zip_file")"
                    unzip -q -o -d "$local_dest" "$zip_file" >> "$LOG_FILE" 2>&1 || true
                    touch "$marker"
                fi
            fi
        done
    fi

    local count_after
    count_after="$(count_files "$local_dest")"
    local diff=$(( count_after - count_before ))
    if [ "$diff" -lt 0 ]; then diff=0; fi

    log "[SYNC] $label sync finished. New files acquired: $diff (Total: $count_after)"
    echo "$diff"
}

# ------------------------------------------------------------------------------
# 4. Pipeline Trigger Hook
# ------------------------------------------------------------------------------
trigger_downstream_pipelines() {
    local new_sms_count="$1"
    local new_audio_count="$2"

    if [ "$RUN_PIPELINE" = "0" ]; then
        log "[PIPELINE] Pipeline execution disabled (--no-pipeline)."
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "[DRY-RUN] Pipeline execution skipped in dry-run mode."
        return 0
    fi

    # 1. SMS / Call Ingestion Trigger
    if [ "$new_sms_count" -gt 0 ] || [ "$FORCE_PIPELINE" = "1" ]; then
        log "[PIPELINE] Triggering SMS/Call ingestion pipeline..."
        if [ -n "$OVERRIDE_SMS_INGEST_SCRIPT" ] && [ -f "$OVERRIDE_SMS_INGEST_SCRIPT" ]; then
            log "[PIPELINE] Running override script: $OVERRIDE_SMS_INGEST_SCRIPT"
            "$PYTHON_BIN" "$OVERRIDE_SMS_INGEST_SCRIPT" >> "$LOG_FILE" 2>&1 || {
                log "[ERROR] Override SMS ingest script failed."
            }
        elif [ -f "${REPO_ROOT}/core/ingest_sms.py" ]; then
            log "[PIPELINE] Running core/ingest_sms.py..."
            (cd "$REPO_ROOT" && "$PYTHON_BIN" "core/ingest_sms.py" >> "$LOG_FILE" 2>&1) || {
                log "[WARN] core/ingest_sms.py finished with warnings/errors (see $LOG_FILE)."
            }
        else
            log "[WARN] core/ingest_sms.py not found. Skipping SMS pipeline."
        fi
    fi

    # 2. Audio Diarization / Transcription Trigger
    if [ "$new_audio_count" -gt 0 ] || [ "$FORCE_PIPELINE" = "1" ]; then
        if [ "$RUN_DIARIZE" = "1" ] && [ -f "${REPO_ROOT}/core/batch_diarize.py" ]; then
            log "[PIPELINE] New audio files detected. Launching detached diarization session 'aim_diarize' via tmux..."
            if command -v tmux >/dev/null 2>&1; then
                if tmux has-session -t aim_diarize 2>/dev/null; then
                    log "[INFO] Tmux session 'aim_diarize' is already running. Not launching a duplicate."
                else
                    tmux new-session -d -s aim_diarize "cd '$REPO_ROOT' && '$PYTHON_BIN' core/batch_diarize.py >> '$LOG_FILE' 2>&1"
                    log "[SUCCESS] Tmux session 'aim_diarize' spawned in detached background."
                fi
            else
                log "[WARN] Tmux not installed; cannot launch detached audio diarization safely."
            fi
        else
            log "[PIPELINE] New audio files downloaded. (Run with --run-diarize to auto-spawn diarization)."
        fi
    fi
}

run_cycle() {
    log "=================================================================="
    log "A.I.M. Background Sync Cycle Started"
    log "=================================================================="

    local new_sms=0
    local new_audio=0

    # Sync primary SMS XML source
    local sms_diff1
    sms_diff1="$(sync_source "$GDRIVE_SMS_PATH" "$LOCAL_SMS_DIR" "SMS/Texts" | tail -n 1)"
    new_sms=$(( new_sms + sms_diff1 ))

    # Sync secondary Ad-Free SMS source (if configured and distinct)
    if [ "$GDRIVE_ADFREE_SMS_PATH" != "$GDRIVE_SMS_PATH" ]; then
        local sms_diff2
        sms_diff2="$(sync_source "$GDRIVE_ADFREE_SMS_PATH" "$LOCAL_SMS_DIR" "Ad-Free SMS Backups" | tail -n 1)"
        new_sms=$(( new_sms + sms_diff2 ))
    fi

    # Sync Audio source
    local audio_diff
    audio_diff="$(sync_source "$GDRIVE_AUDIO_PATH" "$LOCAL_AUDIO_DIR" "Audio/TalkerACR" | tail -n 1)"
    new_audio=$(( new_audio + audio_diff ))

    # Trigger downstream pipelines if new data was detected
    trigger_downstream_pipelines "$new_sms" "$new_audio"

    log "[CYCLE COMPLETE] Sync summary: SMS files: +$new_sms | Audio files: +$new_audio"
}

# ------------------------------------------------------------------------------
# 5. Service Installation & Helper Commands
# ------------------------------------------------------------------------------
install_systemd() {
    echo "=== Installing A.I.M. Systemd User Service and Timer ==="
    local target_root="$REPO_ROOT"
    local git_common
    git_common="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
    if [ -n "$git_common" ]; then
        target_root="$(cd "$(dirname "$git_common")" && pwd)"
    fi

    local user_systemd_dir="$HOME/.config/systemd/user"
    mkdir -p "$user_systemd_dir"

    local service_dest="$user_systemd_dir/aim-sync.service"
    local timer_dest="$user_systemd_dir/aim-sync.timer"

    cat <<EOF > "$service_dest"
[Unit]
Description=A.I.M. Calendar Background Sync Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$target_root
ExecStart=/bin/bash $target_root/core/sync_daemon.sh --once
StandardOutput=append:$target_root/sync_daemon.log
StandardError=append:$target_root/sync_daemon.log

[Install]
WantedBy=default.target
EOF

    cat <<EOF > "$timer_dest"
[Unit]
Description=A.I.M. Calendar Periodic Background Sync Timer
ConditionPathExists=$target_root/core/sync_daemon.sh

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

    echo "[*] Units created at:"
    echo "    $service_dest"
    echo "    $timer_dest"

    if command -v systemctl >/dev/null 2>&1; then
        echo "[*] Reloading systemd user daemon..."
        systemctl --user daemon-reload
        echo "[*] Enabling and starting aim-sync.timer..."
        systemctl --user enable --now aim-sync.timer
        echo "[SUCCESS] aim-sync.timer is active!"
        systemctl --user status aim-sync.timer --no-pager || true
    else
        echo "[WARN] systemctl command not found. Units installed but not enabled."
    fi
}

install_cron() {
    echo "=== A.I.M. Sync Daemon Crontab Configuration ==="
    local target_root="$REPO_ROOT"
    local git_common
    git_common="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
    if [ -n "$git_common" ]; then
        target_root="$(cd "$(dirname "$git_common")" && pwd)"
    fi

    local cron_line="*/15 * * * * /bin/bash $target_root/core/sync_daemon.sh --once >> $target_root/sync_daemon.log 2>&1"
    echo ""
    echo "To run every 15 minutes via cron, add the following line to 'crontab -e':"
    echo ""
    echo "$cron_line"
    echo ""
}

show_status() {
    echo "=== A.I.M. Sync Daemon Status ==="
    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid="$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "Status: RUNNING (PID: $pid)"
        else
            echo "Status: STALE LOCK (PID: $pid not running)"
        fi
    else
        echo "Status: IDLE (No active sync process running)"
    fi

    if command -v systemctl >/dev/null 2>&1; then
        echo ""
        echo "--- Systemd Timer Status ---"
        systemctl --user status aim-sync.timer --no-pager 2>/dev/null || echo "Timer not installed or not running."
    fi

    if [ -f "$LOG_FILE" ]; then
        echo ""
        echo "--- Recent Log Entries ($LOG_FILE) ---"
        tail -n 15 "$LOG_FILE"
    fi
}

show_help() {
    cat <<EOF
Usage: core/sync_daemon.sh [OPTIONS]

A.I.M. Calendar Background Sync Daemon. Synchronizes Google Drive communication
records (Audio and SMS) to the local repository and triggers incremental ingestion.

Options:
  --once               Run a single sync cycle and exit (Default, ideal for cron/systemd).
  --loop [SECONDS]     Run continuously in a loop, sleeping SECONDS between cycles (default 300s).
  --dry-run            Simulate rclone sync without making local changes or running pipelines.
  --no-pipeline        Perform rclone sync only; do not trigger downstream ingestion scripts.
  --force-pipeline     Trigger downstream ingestion even if no new files were acquired.
  --run-diarize        Automatically launch detached Pyannote/Whisper diarization if audio is synced.
  --install-systemd    Install and activate the systemd user service and timer (aim-sync.timer).
  --install-cron       Show the recommended crontab entry for scheduled execution.
  --status             Show daemon lock status, systemd timer status, and recent logs.
  -h, --help           Show this help documentation.

Environment Variables:
  GDRIVE_REMOTE            rclone remote prefix (default: gdrive:)
  GDRIVE_AUDIO_PATH        Remote audio path (default: gdrive:TalkerACR/All)
  GDRIVE_SMS_PATH          Remote SMS path (default: gdrive:sms=backup-jess)
  GDRIVE_ADFREE_SMS_PATH   Secondary SMS path (default: gdrive:Ad-Free SMS Backups)
  LOCAL_AUDIO_DIR          Destination for audio (default: TalkerACR/All)
  LOCAL_SMS_DIR            Destination for texts (default: conversations/sms_raw)
  LOG_FILE                 Path to log file (default: sync_daemon.log)
  LOCK_FILE                Path to lockfile (default: /tmp/aim_sync_daemon.lock)

EOF
}

# ------------------------------------------------------------------------------
# 6. Command Line Argument Parser
# ------------------------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --once)
            MODE="once"
            shift
            ;;
        --loop)
            MODE="loop"
            if [ $# -gt 1 ] && [[ "$2" =~ ^[0-9]+$ ]]; then
                LOOP_INTERVAL="$2"
                shift 2
            else
                shift
            fi
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --no-pipeline)
            RUN_PIPELINE=0
            shift
            ;;
        --force-pipeline)
            FORCE_PIPELINE=1
            shift
            ;;
        --run-diarize)
            RUN_DIARIZE=1
            shift
            ;;
        --install-systemd)
            install_systemd
            exit 0
            ;;
        --install-cron)
            install_cron
            exit 0
            ;;
        --status)
            show_status
            exit 0
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            show_help
            exit 1
            ;;
    esac
done

# ------------------------------------------------------------------------------
# 7. Main Execution Flow
# ------------------------------------------------------------------------------
acquire_lock

if [ "$MODE" = "once" ]; then
    run_cycle
elif [ "$MODE" = "loop" ]; then
    log "[DAEMON] Entering continuous loop mode (Interval: ${LOOP_INTERVAL}s). Press Ctrl+C to stop."
    while true; do
        run_cycle
        log "[DAEMON] Sleeping for ${LOOP_INTERVAL}s until next sync cycle..."
        sleep "$LOOP_INTERVAL"
    done
fi
