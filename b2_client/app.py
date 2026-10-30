from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import uuid

import streamlit as st

from b2_backend import (
    B2Backend,
    human_size,
)
from transfer_manager import (
    ACTIVE,
    TransferManager,
    copy_move_operation,
    download_operation,
    upload_file_operation,
    upload_folder_operation,
)


BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="B2 Client",
    page_icon="☁️",
    layout="wide",
)

st.title("Backblaze B2 Client")
st.caption("Streamlit-controlled transfers • up to three simultaneous transfers")


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
# App/session setup
# ============================================================

@st.cache_resource
def get_transfer_manager() -> TransferManager:
    return TransferManager(limit=3, disconnect_timeout=5.0)


manager = get_transfer_manager()

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

session_id = st.session_state.session_id
manager.heartbeat(session_id)
# A full script run means the user performed an action. Active transfers stay;
# prior results disappear. Fragment-only progress refreshes do not clear them.
if st.session_state.pop("_system_transfer_rerun", False):
    pass
else:
    manager.clear_terminal(session_id)


def pct(current: int, total: int) -> int:
    if total <= 0:
        return 0
    return min(100, max(0, int(current * 100 / total)))


@st.fragment(run_every="1s")
def transfer_panel():
    manager.heartbeat(session_id)
    active_now = manager.active_count()
    active_before = st.session_state.get("_active_transfer_count", active_now)
    st.session_state._active_transfer_count = active_now
    if active_before >= 3 and active_now < 3:
        # Re-enable the Start buttons without treating this automatic refresh
        # as a user action that clears the completed result.
        st.session_state._system_transfer_rerun = True
        st.rerun(scope="app")
    for info in manager.list(session_id):
        status = info["status"]
        total = int(info.get("total_bytes", 0))
        done = int(info.get("transferred_bytes", 0))
        percent = pct(done, total)
        st.progress(percent, text=f"{info['label']}: {percent}% ({status})")
        if info.get("current_file"):
            st.caption(info["current_file"])
        if info.get("total_files"):
            st.caption(
                f"Files: {info.get('processed_files', 0)} / {info['total_files']} • "
                f"Uploaded: {info.get('uploaded', 0)} • Skipped: {info.get('skipped', 0)} • "
                f"Failed: {info.get('failed', 0)}"
            )
        if status in ACTIVE:
            if st.button("Stop", key=f"stop_{info['id']}"):
                manager.stop(session_id, info["id"])
                st.rerun()
        elif status == "complete":
            st.success("Complete")
        elif status == "skipped":
            st.info("Skipped because the destination has the same size.")
        elif status == "completed_with_errors":
            st.warning("Completed with errors")
            if info.get("error"):
                st.code(info["error"])
        elif status == "error":
            st.error("Transfer failed")
            if info.get("error"):
                st.code(info["error"])


def user_action() -> None:
    manager.clear_terminal(session_id)


def can_start_transfer() -> bool:
    return manager.active_count() < 3

for key, default in {
    "prefix": "",
    "upload_local_path": "",
    "upload_folder_local_path": "",
    "download_local_path": "",
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
    ]
)

transfer_panel()


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

    browse_refresh = st.button("Refresh", key="browse_refresh")
    if browse_refresh:
        user_action()
        try:
            folders, objects = b2.list_folder(prefix)
            stats = b2.get_prefix_stats(prefix)
            st.session_state.browse_cache = (prefix, folders, objects, stats)
        except Exception as error:
            st.exception(error)

    cached = st.session_state.get("browse_cache")
    if cached and cached[0] == prefix:
        _, folders, objects, stats = cached
    else:
        folders, objects = [], []
        stats = {"size": 0, "objects": 0, "child_folders": {}}
        st.info("Press Refresh to load this folder.")

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

    if st.button(
        "Upload",
        type="primary",
        disabled=not can_start_transfer(),
        key="start_upload_file",
    ):
        user_action()
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
            manager.start(
                session_id,
                "upload_file",
                f"Upload {Path(local_path).name}",
                upload_file_operation(manager, local_path, remote_key.strip("/")),
            )

            st.rerun()

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

    st.caption("Existing same-size objects are skipped; different-size objects are overwritten.")

    if st.button(
        "Upload folder",
        type="primary",
        disabled=not can_start_transfer(),
        key="start_upload_folder",
    ):
        user_action()
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
            manager.start(
                session_id,
                "upload_folder",
                f"Upload folder {Path(folder_path).name}",
                upload_folder_operation(manager, folder_path, remote_prefix.strip("/")),
            )

            st.rerun()

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

    if st.button(
        "Download",
        type="primary",
        disabled=not can_start_transfer(),
        key="start_download",
    ):
        user_action()
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
            manager.start(
                session_id,
                "download",
                f"Download {Path(remote_key).name}",
                download_operation(manager, remote_key.strip("/"), local_path),
            )

            st.rerun()

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

        if st.button("Refresh", key="copy_browser_refresh"):
            user_action()
            try:
                browser_folders, browser_objects = b2.list_folder(browser_prefix)
                st.session_state.copy_browser_cache = (
                    browser_prefix,
                    browser_folders,
                    browser_objects,
                )
            except Exception as error:
                st.exception(error)

        copy_cache = st.session_state.get("copy_browser_cache")
        if copy_cache and copy_cache[0] == browser_prefix:
            _, browser_folders, browser_objects = copy_cache
        else:
            browser_folders, browser_objects = [], []
            st.info("Press Refresh to load this folder.")

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

    if st.button(
        action,
        type="primary",
        disabled=not can_start_transfer() or not move_confirmed,
        key="start_copy_move",
    ):
        user_action()
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
            manager.start(
                session_id,
                "copy_move",
                f"{action} {source_key}",
                copy_move_operation(
                    manager,
                    source_key,
                    destination_key,
                    source_is_folder,
                    action == "Move",
                    overwrite,
                ),
            )
            st.rerun()
