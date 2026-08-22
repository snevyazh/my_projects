from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time

import streamlit as st

from b2_backend import (
    B2Backend,
    human_size,
)


BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / ".transfer_state"
WORKER_FILE = BASE_DIR / "transfer_worker.py"

st.set_page_config(
    page_title="B2 Client",
    page_icon="☁️",
    layout="wide",
)

st.title("Backblaze B2 Client")
st.caption("Single-threaded API calls • transfer worker runs as a separate process • folder-picker callback build • recursive size build • stale-state fix v3")


# ============================================================
# Local path helpers
# ============================================================

def clean_local_path(value: str) -> str:
    value = (value or "").strip()
    value = value.strip('"').strip("'")
    return os.path.normpath(value)


def choose_with_zenity(*options: str) -> tuple[bool, str | None]:
    """Return (available, selection) for a native Linux Zenity dialog."""
    if os.name == "nt":
        return False, None

    executable = shutil.which("zenity")

    if not executable:
        return False, None

    result = subprocess.run(
        [executable, "--file-selection", *options],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        return True, result.stdout.rstrip("\r\n") or None

    # Zenity uses exit code 1 when the user closes or cancels the dialog.
    if result.returncode == 1:
        return True, None

    raise RuntimeError(result.stderr.strip() or "Zenity could not open the dialog.")


def choose_file() -> str | None:
    """
    Native selector executed synchronously on Streamlit's main script thread.

    No transfer thread is involved.
    """
    try:
        available, selected = choose_with_zenity(
            "--title=Choose a file",
        )

        if available:
            return selected

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()

        selected = filedialog.askopenfilename(
            parent=root,
        )

        root.destroy()

        return selected or None

    except Exception as error:
        st.error(
            "Could not open file selector: "
            f"{error}"
        )
        return None


def choose_folder() -> str | None:
    """Open a native folder selector on Linux or Windows."""
    try:
        available, selected = choose_with_zenity(
            "--directory",
            "--title=Choose a folder",
        )

        if available:
            return selected

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askdirectory(parent=root)
        root.destroy()

        return selected or None

    except Exception as error:
        st.error("Could not open folder selector: " f"{error}")
        return None


def choose_save_file(
    initial_name: str = "",
) -> str | None:
    try:
        zenity_options = [
            "--save",
            "--confirm-overwrite",
            "--title=Choose destination",
        ]

        if initial_name:
            zenity_options.append(f"--filename={initial_name}")

        available, selected = choose_with_zenity(*zenity_options)

        if available:
            return selected

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()

        selected = filedialog.asksaveasfilename(
            parent=root,
            initialfile=initial_name,
        )

        root.destroy()

        return selected or None

    except Exception as error:
        st.error(
            "Could not open save selector: "
            f"{error}"
        )
        return None

def open_copy_browser_folder(prefix: str):
    st.session_state["copy_browser_prefix"] = prefix


def use_copy_source(key: str, source_type: str):
    st.session_state["copy_move_source_type"] = source_type
    st.session_state["copy_move_source_key"] = key.rstrip("/")


def use_copy_destination(prefix: str):
    prefix = prefix.rstrip("/")
    source_type = st.session_state.get("copy_move_source_type", "File")
    source_key = st.session_state.get("copy_move_source_key", "").strip("/")

    if source_type == "File" and source_key:
        filename = source_key.rsplit("/", 1)[-1]
        st.session_state["copy_move_destination_key"] = (
            f"{prefix}/{filename}" if prefix else filename
        )
    else:
        st.session_state["copy_move_destination_key"] = prefix


# ============================================================
# Transfer state
# ============================================================

def ensure_state_dir():
    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def status_path(kind: str) -> Path:
    return STATE_DIR / f"{kind}.json"


def stop_path(kind: str) -> Path:
    return STATE_DIR / f"{kind}.stop"


def clear_transfer_files(kind: str):
    for path in [
        status_path(kind),
        stop_path(kind),
    ]:
        if path.exists():
            path.unlink()


def read_status(kind: str) -> dict | None:
    path = status_path(kind)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

    except Exception:
        return None


def write_status(
    kind: str,
    info: dict,
):
    path = status_path(kind)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        json.dumps(
            info,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path,
    )


def process_is_running(
    pid: int | None,
) -> bool:
    """
    Check whether a worker PID is still alive.

    On Windows, os.kill(pid, 0) is not a reliable existence check and can
    raise SystemError. Use tasklist instead. On non-Windows systems, fall
    back to os.kill(pid, 0).
    """
    if not pid:
        return False

    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    if os.name == "nt":
        try:
            creationflags = 0

            if hasattr(
                subprocess,
                "CREATE_NO_WINDOW",
            ):
                creationflags = (
                    subprocess.CREATE_NO_WINDOW
                )

            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {pid}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                timeout=10,
            )

            output = result.stdout.strip()

            if not output:
                return False

            if (
                "No tasks are running"
                in output
            ):
                return False

            # CSV output for a live process begins with its image name.
            return str(pid) in output

        except Exception:
            # If Windows process inspection itself fails, do not crash the UI.
            # Treat the state as stale rather than leaving the app unusable.
            return False

    try:
        os.kill(
            pid,
            0,
        )
        return True

    except ProcessLookupError:
        return False

    except PermissionError:
        return True

    except OSError:
        return False


def reconcile_status(
    kind: str,
) -> dict | None:
    """
    Prevent an old JSON status file from leaving the UI permanently stuck
    in "running" after Streamlit or a worker was stopped.

    Older builds did not store a worker PID, so any old "running" record
    without a PID is automatically treated as interrupted.
    """
    info = read_status(kind)

    if not info:
        return None

    status = info.get(
        "status",
        "unknown",
    )

    if status not in {
        "starting",
        "running",
        "stopping",
        "deleting",
    }:
        return info

    pid = info.get("pid")

    if not process_is_running(pid):
        info["status"] = "interrupted"
        info["error"] = (
            "The previous transfer is no longer running. "
            "Its saved progress record was stale."
        )

        write_status(
            kind,
            info,
        )

        stale_stop = stop_path(kind)

        if stale_stop.exists():
            try:
                stale_stop.unlink()
            except OSError:
                pass

    return info


def reset_transfer_state(
    kind: str,
):
    clear_transfer_files(kind)


def start_worker(
    *,
    kind: str,
    mode: str,
    local_path: str,
    remote_key: str = "",
    remote_prefix: str = "",
    skip_same: bool = False,
    source_key: str = "",
    destination_key: str = "",
    source_is_folder: bool = False,
    move: bool = False,
    overwrite: bool = False,
):
    ensure_state_dir()
    clear_transfer_files(kind)

    command = [
        sys.executable,
        str(WORKER_FILE),
        mode,
        "--status-file",
        str(status_path(kind)),
        "--stop-file",
        str(stop_path(kind)),
        "--local-path",
        local_path,
    ]

    if remote_key:
        command.extend(
            [
                "--remote-key",
                remote_key,
            ]
        )

    if remote_prefix:
        command.extend(
            [
                "--remote-prefix",
                remote_prefix,
            ]
        )

    if skip_same:
        command.append(
            "--skip-same"
        )

    if source_key:
        command.extend(
            [
                "--source-key",
                source_key,
            ]
        )

    if destination_key:
        command.extend(
            [
                "--destination-key",
                destination_key,
            ]
        )

    if source_is_folder:
        command.append(
            "--source-is-folder"
        )

    if move:
        command.append(
            "--move"
        )

    if overwrite:
        command.append(
            "--overwrite"
        )

    creationflags = 0

    if hasattr(
        subprocess,
        "CREATE_NO_WINDOW",
    ):
        creationflags = (
            subprocess.CREATE_NO_WINDOW
        )

    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        creationflags=creationflags,
    )

    # Close the brief gap between process creation and the worker's first
    # status update so a rapid rerun cannot start a duplicate transfer.
    initial_status = {
        "status": "starting",
        "started_at": time.time(),
        "heartbeat": time.time(),
        "pid": process.pid,
        "total_bytes": 0,
        "transferred_bytes": 0,
        "total_files": 0,
        "processed_files": 0,
        "current_file": "",
        "current_bytes": 0,
        "current_size": 0,
        "uploaded": 0,
        "skipped": 0,
        "copied": 0,
        "deleted": 0,
        "failed": 0,
        "error": "",
        "source_is_folder": source_is_folder,
        "action": "move" if move else "copy",
    }

    if not status_path(kind).exists():
        write_status(kind, initial_status)


def request_stop(kind: str):
    ensure_state_dir()

    stop_path(kind).write_text(
        "stop",
        encoding="utf-8",
    )


def pct(
    current: int,
    total: int,
) -> int:
    if total <= 0:
        return 0

    return min(
        100,
        max(
            0,
            int(current * 100 / total),
        ),
    )


def render_transfer_status(
    kind: str,
    label: str,
    folder: bool = False,
):
    info = reconcile_status(kind)

    if not info:
        return

    status = info.get(
        "status",
        "unknown",
    )

    overall = pct(
        int(
            info.get(
                "transferred_bytes",
                0,
            )
        ),
        int(
            info.get(
                "total_bytes",
                0,
            )
        ),
    )

    st.progress(
        overall,
        text=(
            f"{label}: {overall}%"
            if status == "running"
            else f"{label}: {status}"
        ),
    )

    if folder:
        current = pct(
            int(
                info.get(
                    "current_bytes",
                    0,
                )
            ),
            int(
                info.get(
                    "current_size",
                    0,
                )
            ),
        )

        st.progress(
            current,
            text=f"Current file: {current}%",
        )

        if info.get("current_file"):
            st.write(
                "Current: "
                f"`{info['current_file']}`"
            )

        if kind == "copy_move":
            st.write(
                f"Files processed: "
                f"{info.get('processed_files', 0)} / "
                f"{info.get('total_files', 0)}  |  "
                f"Processed: "
                f"{human_size(int(info.get('transferred_bytes', 0)))} / "
                f"{human_size(int(info.get('total_bytes', 0)))}"
            )
        else:
            st.write(
                f"Files processed: "
                f"{info.get('processed_files', 0)} / "
                f"{info.get('total_files', 0)}  |  "
                f"Uploaded: {info.get('uploaded', 0)}  |  "
                f"Skipped: {info.get('skipped', 0)}  |  "
                f"Failed: {info.get('failed', 0)}  |  "
                f"Processed: "
                f"{human_size(int(info.get('transferred_bytes', 0)))} / "
                f"{human_size(int(info.get('total_bytes', 0)))}"
            )

    else:
        st.write(
            f"{human_size(int(info.get('transferred_bytes', 0)))} / "
            f"{human_size(int(info.get('total_bytes', 0)))}"
        )

    if kind == "copy_move":
        st.write(
            f"Copied: {info.get('copied', 0)}  |  "
            f"Deleted: {info.get('deleted', 0)}  |  "
            f"Failed: {info.get('failed', 0)}"
        )

    if status in {"starting", "running"}:
        if st.button(
            f"⏹ Stop {label.lower()}",
            key=f"stop_{kind}",
        ):
            request_stop(kind)
            st.rerun()

    elif status == "deleting":
        st.info("Copy complete. Deleting source objects…")

    elif status == "cancelled":
        st.warning(
            f"{label} stopped."
        )

        if st.button(
            "Clear transfer status",
            key=f"clear_{kind}_cancelled",
        ):
            reset_transfer_state(kind)
            st.rerun()

    elif status == "interrupted":
        st.warning(
            f"{label} was interrupted. "
            "The old running state has been cleared."
        )

        if st.button(
            "Clear transfer status",
            key=f"clear_{kind}_interrupted",
        ):
            reset_transfer_state(kind)
            st.rerun()

    elif status == "complete":
        st.success(
            f"{label} complete."
        )

        if st.button(
            "Clear transfer status",
            key=f"clear_{kind}_complete",
        ):
            reset_transfer_state(kind)
            st.rerun()

    elif status == "completed_with_errors":
        st.warning(
            f"{label} finished with {info.get('failed', 0)} error(s)."
        )

        if info.get("error"):
            st.code(info["error"])

        if st.button(
            "Clear transfer status",
            key=f"clear_{kind}_completed_with_errors",
        ):
            reset_transfer_state(kind)
            st.rerun()

    elif status == "error":
        st.error(
            f"{label} failed."
        )
        st.code(
            info.get(
                "error",
                "Unknown error",
            )
        )

        if st.button(
            "Clear transfer status",
            key=f"clear_{kind}_error",
        ):
            reset_transfer_state(kind)
            st.rerun()


# ============================================================
# App/session setup
# ============================================================

ensure_state_dir()

for key, default in {
    "prefix": "",
    "upload_local_path": "",
    "upload_folder_local_path": "",
    "download_local_path": "",
    "verify_local_folder": "",
    "copy_browser_prefix": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


try:
    b2 = B2Backend()
except Exception as error:
    st.error(str(error))
    st.stop()


with st.sidebar:
    st.subheader("Connection")

    if st.button(
        "Test connection",
        use_container_width=True,
    ):
        try:
            b2.test_connection()
            st.success("Connection OK")
        except Exception as error:
            st.exception(error)

    st.caption(
        f"Bucket: `{b2.bucket}`"
    )


tabs = st.tabs(
    [
        "Browse",
        "Upload file",
        "Upload folder",
        "Download",
        "Copy / move",
        "Verify",
    ]
)


# ============================================================
# Browse
# ============================================================

with tabs[0]:
    prefix = st.session_state.prefix

    st.write(
        "Current path:",
        f"`/{prefix}`" if prefix else "`/`",
    )

    if prefix:
        if st.button(
            "⬆ Up",
            key="browse_up",
        ):
            parts = (
                prefix
                .rstrip("/")
                .split("/")
            )

            st.session_state.prefix = (
                "/".join(parts[:-1])
            )

            if st.session_state.prefix:
                st.session_state.prefix += "/"

            st.rerun()

    try:
        folders, objects = b2.list_folder(prefix)
        stats = b2.get_prefix_stats(prefix)

    except Exception as error:
        st.exception(error)
        folders = []
        objects = []
        stats = {
            "size": 0,
            "objects": 0,
            "child_folders": {},
        }

    metric1, metric2 = st.columns(2)

    metric1.metric(
        "Total volume",
        human_size(
            int(stats.get("size", 0))
        ),
    )

    metric2.metric(
        "Objects",
        int(
            stats.get("objects", 0)
        ),
    )

    st.caption(
        "Folder sizes are recursive totals for everything below each folder."
    )

    if folders:
        st.subheader("Folders")

        for folder in folders:
            display = (
                folder[len(prefix):]
                if prefix
                else folder
            ).rstrip("/")

            folder_stats = (
                stats
                .get("child_folders", {})
                .get(
                    folder,
                    {
                        "size": 0,
                        "objects": 0,
                    },
                )
            )

            cols = st.columns([6, 2, 2])

            with cols[0]:
                if st.button(
                    f"📁 {display}",
                    key=f"folder_{folder}",
                    use_container_width=True,
                ):
                    st.session_state.prefix = folder
                    st.rerun()

            cols[1].write(
                human_size(
                    int(
                        folder_stats.get(
                            "size",
                            0,
                        )
                    )
                )
            )

            cols[2].write(
                f"{int(folder_stats.get('objects', 0))} files"
            )

    st.subheader("Files")

    if not objects:
        st.info("No files here.")

    for obj in objects:
        name = (
            obj.key[len(prefix):]
            if prefix
            else obj.key
        )

        cols = st.columns([6, 2, 2])

        cols[0].write(
            f"📄 {name}"
        )

        cols[1].write(
            human_size(obj.size)
        )

        cols[2].write(
            obj.last_modified.strftime(
                "%Y-%m-%d %H:%M"
            )
            if obj.last_modified
            else ""
        )


# ============================================================
# Upload file
# ============================================================

with tabs[1]:
    st.subheader("Upload one file")

    if st.button(
        "📂 Choose file",
        key="choose_file",
    ):
        selected = choose_file()

        if selected:
            st.session_state.upload_local_path = selected

    local_path = st.text_input(
        "Local file path",
        key="upload_local_path",
    )

    remote_key = st.text_input(
        "Remote object key",
        key="upload_remote_key",
        placeholder="TV_S/Poirot/S01/E01.mkv",
    )

    current = reconcile_status(
        "upload_file"
    )

    active = (
        current
        and current.get("status")
        in {"starting", "running"}
    )

    if st.button(
        "Upload",
        type="primary",
        disabled=bool(active),
        key="start_upload_file",
    ):
        local_path = (
            clean_local_path(
                local_path
            )
        )

        if not Path(
            local_path
        ).is_file():
            st.error(
                "File does not exist: "
                f"{local_path}"
            )

        elif not remote_key:
            st.warning(
                "Enter a remote object key."
            )

        else:
            start_worker(
                kind="upload_file",
                mode="upload_file",
                local_path=local_path,
                remote_key=remote_key.strip("/"),
            )

            st.rerun()

    @st.fragment(
        run_every="500ms"
    )
    def upload_file_status():
        render_transfer_status(
            "upload_file",
            "Upload",
        )

    upload_file_status()


# ============================================================
# Upload folder
# ============================================================

with tabs[2]:
    st.subheader(
        "Upload folder recursively"
    )

    if st.button(
        "📂 Choose folder",
        key="choose_upload_folder",
    ):
        selected = choose_folder()

        if selected:
            st.session_state["upload_folder_local_path"] = selected

    folder_path = st.text_input(
        "Local folder",
        key="upload_folder_local_path",
    )

    remote_prefix = st.text_input(
        "Remote prefix (optional)",
        key="upload_folder_prefix",
    )

    skip_same = st.checkbox(
        "Skip existing objects with same size",
        value=True,
        key="skip_same_folder",
    )

    current = reconcile_status(
        "upload_folder"
    )

    active = (
        current
        and current.get("status")
        in {"starting", "running"}
    )

    if st.button(
        "Upload folder",
        type="primary",
        disabled=bool(active),
        key="start_upload_folder",
    ):
        folder_path = (
            clean_local_path(
                folder_path
            )
        )

        if not Path(
            folder_path
        ).is_dir():
            st.error(
                "Folder does not exist: "
                f"{folder_path}"
            )

        else:
            start_worker(
                kind="upload_folder",
                mode="upload_folder",
                local_path=folder_path,
                remote_prefix=remote_prefix.strip("/"),
                skip_same=skip_same,
            )

            st.rerun()

    @st.fragment(
        run_every="500ms"
    )
    def upload_folder_status():
        render_transfer_status(
            "upload_folder",
            "Folder upload",
            folder=True,
        )

    upload_folder_status()


# ============================================================
# Download
# ============================================================

with tabs[3]:
    st.subheader(
        "Download one object"
    )

    remote_key = st.text_input(
        "Remote object key",
        key="download_remote_key",
    )

    if st.button(
        "📁 Choose destination",
        key="choose_download_destination",
    ):
        selected = choose_save_file(
            Path(remote_key).name
            if remote_key
            else ""
        )

        if selected:
            st.session_state.download_local_path = selected

    local_path = st.text_input(
        "Local destination",
        key="download_local_path",
    )

    current = reconcile_status(
        "download"
    )

    active = (
        current
        and current.get("status")
        in {"starting", "running"}
    )

    if st.button(
        "Download",
        type="primary",
        disabled=bool(active),
        key="start_download",
    ):
        local_path = (
            clean_local_path(
                local_path
            )
        )

        if not remote_key:
            st.warning(
                "Enter a remote object key."
            )

        elif not local_path:
            st.warning(
                "Choose a destination."
            )

        else:
            start_worker(
                kind="download",
                mode="download",
                local_path=local_path,
                remote_key=remote_key.strip("/"),
            )

            st.rerun()

    @st.fragment(
        run_every="500ms"
    )
    def download_status():
        render_transfer_status(
            "download",
            "Download",
        )

    download_status()


# ============================================================
# Copy / move inside B2
# ============================================================

with tabs[4]:
    st.subheader("Copy or move inside B2")
    st.caption(
        "Folder operations are recursive. The destination prefix receives "
        "the contents of the source prefix."
    )

    with st.expander("🔎 Browse B2 keys", expanded=True):
        browser_prefix = st.session_state.copy_browser_prefix
        st.caption("Select the source first, then choose its destination folder.")
        st.write(
            "Current folder:",
            f"`/{browser_prefix}`" if browser_prefix else "`/`",
        )

        browser_actions = st.columns([1, 2, 5])

        if browser_prefix:
            browser_parts = browser_prefix.rstrip("/").split("/")
            parent_prefix = "/".join(browser_parts[:-1])

            if parent_prefix:
                parent_prefix += "/"

            browser_actions[0].button(
                "⬆ Up",
                key="copy_browser_up",
                on_click=open_copy_browser_folder,
                args=(parent_prefix,),
                use_container_width=True,
            )

        browser_actions[1].button(
            "Use as destination",
            key="copy_browser_use_current_destination",
            on_click=use_copy_destination,
            args=(browser_prefix,),
            use_container_width=True,
        )

        try:
            browser_folders, browser_objects = b2.list_folder(browser_prefix)
        except Exception as error:
            st.exception(error)
            browser_folders = []
            browser_objects = []

        if browser_folders:
            st.caption("Folders")

        for index, folder in enumerate(browser_folders):
            display = (
                folder[len(browser_prefix):]
                if browser_prefix
                else folder
            ).rstrip("/")
            row = st.columns([5, 1, 1, 1])
            row[0].write(f"📁 {display}")
            row[1].button(
                "Open",
                key=f"copy_browser_open_{index}",
                on_click=open_copy_browser_folder,
                args=(folder,),
                use_container_width=True,
            )
            row[2].button(
                "Source",
                key=f"copy_browser_source_folder_{index}",
                on_click=use_copy_source,
                args=(folder, "Folder"),
                use_container_width=True,
            )
            row[3].button(
                "Destination",
                key=f"copy_browser_destination_folder_{index}",
                on_click=use_copy_destination,
                args=(folder,),
                use_container_width=True,
            )

        if browser_objects:
            st.caption("Files")

        for index, obj in enumerate(browser_objects):
            display = (
                obj.key[len(browser_prefix):]
                if browser_prefix
                else obj.key
            )
            row = st.columns([6, 2, 2])
            row[0].write(f"📄 {display}")
            row[1].write(human_size(obj.size))
            row[2].button(
                "Use as source",
                key=f"copy_browser_source_file_{index}",
                on_click=use_copy_source,
                args=(obj.key, "File"),
                use_container_width=True,
            )

        if not browser_folders and not browser_objects:
            st.info("This folder is empty.")

    source_type = st.radio(
        "Source type",
        ["File", "Folder"],
        horizontal=True,
        key="copy_move_source_type",
    )

    action = st.radio(
        "Action",
        ["Copy", "Move"],
        horizontal=True,
        key="copy_move_action",
    )

    source_key = st.text_input(
        "Source object key" if source_type == "File" else "Source folder prefix",
        key="copy_move_source_key",
        placeholder=(
            "TV_S/Poirot/S01/E01.mkv"
            if source_type == "File"
            else "TV_S/Poirot/S01"
        ),
    )

    destination_key = st.text_input(
        (
            "Destination object key"
            if source_type == "File"
            else "Destination folder prefix"
        ),
        key="copy_move_destination_key",
        placeholder=(
            "Archive/Poirot/S01/E01.mkv"
            if source_type == "File"
            else "Archive/Poirot/S01"
        ),
    )

    overwrite = st.checkbox(
        "Overwrite destination objects if they already exist",
        value=False,
        key="copy_move_overwrite",
    )

    move_confirmed = True

    if action == "Move":
        st.warning(
            "Move deletes the source only after the copy succeeds. A folder "
            "move deletes nothing unless every object was copied successfully."
        )
        move_confirmed = st.checkbox(
            "I understand that the source will be deleted",
            key="copy_move_confirm",
        )

    current = reconcile_status("copy_move")
    active = (
        current
        and current.get("status")
        in {"starting", "running", "deleting"}
    )

    if st.button(
        action,
        type="primary",
        disabled=bool(active) or not move_confirmed,
        key="start_copy_move",
    ):
        source_key = source_key.strip("/")
        destination_key = destination_key.strip("/")
        source_is_folder = source_type == "Folder"

        if not source_key or not destination_key:
            st.warning("Enter both source and destination paths.")

        elif source_key == destination_key:
            st.warning("Source and destination must differ.")

        elif (
            source_is_folder
            and (
                (destination_key + "/").startswith(source_key + "/")
                or (source_key + "/").startswith(destination_key + "/")
            )
        ):
            st.warning("Source and destination folders cannot contain one another.")

        else:
            start_worker(
                kind="copy_move",
                mode="copy_move",
                local_path="",
                source_key=source_key,
                destination_key=destination_key,
                source_is_folder=source_is_folder,
                move=action == "Move",
                overwrite=overwrite,
            )
            st.rerun()

    @st.fragment(run_every="500ms")
    def copy_move_status():
        info = read_status("copy_move")
        render_transfer_status(
            "copy_move",
            "Move" if info and info.get("action") == "move" else "Copy",
            folder=bool(info and info.get("source_is_folder")),
        )

    copy_move_status()


# ============================================================
# Verify
# ============================================================

with tabs[5]:
    st.subheader(
        "Verify local folder against B2"
    )

    if st.button(
        "📂 Choose folder",
        key="choose_verify_folder",
    ):
        selected = choose_folder()

        if selected:
            st.session_state["verify_local_folder"] = selected

    local_folder = st.text_input(
        "Local folder",
        key="verify_local_folder",
    )

    remote_prefix = st.text_input(
        "Remote prefix (optional)",
        key="verify_remote_prefix",
    )

    if st.button(
        "Verify",
        type="primary",
        key="verify_btn",
    ):
        local_folder = (
            clean_local_path(
                local_folder
            )
        )

        if not Path(
            local_folder
        ).is_dir():
            st.error(
                "Folder does not exist: "
                f"{local_folder}"
            )

        else:
            try:
                with st.spinner(
                    "Comparing local files with B2..."
                ):
                    result = (
                        b2.verify_folder_by_size(
                            local_folder,
                            remote_prefix,
                        )
                    )

                st.write(
                    f"Checked: "
                    f"**{result['checked']}**"
                )

                st.write(
                    f"Missing: "
                    f"**{len(result['missing'])}**"
                )

                st.write(
                    f"Size mismatches: "
                    f"**{len(result['mismatched'])}**"
                )

                if (
                    not result["missing"]
                    and not result[
                        "mismatched"
                    ]
                ):
                    st.success(
                        "All checked files match by size."
                    )

                if result["missing"]:
                    st.dataframe(
                        [
                            {"missing": key}
                            for key in result[
                                "missing"
                            ]
                        ],
                        use_container_width=True,
                    )

                if result[
                    "mismatched"
                ]:
                    st.dataframe(
                        [
                            {
                                "key": key,
                                "local_size": local_size,
                                "remote_size": remote_size,
                            }
                            for (
                                key,
                                local_size,
                                remote_size,
                            ) in result[
                                "mismatched"
                            ]
                        ],
                        use_container_width=True,
                    )

            except Exception as error:
                st.exception(error)
