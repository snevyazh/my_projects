import os
import sys
import time
import json
import pandas as pd
import streamlit as st

from gdrive_connector import GoogleDriveConnector, DEFAULT_CHUNK_SIZE
from file_manager import LocalNASFileManager

HISTORY_FILE = "transfer_history.json"

# Page configuration
st.set_page_config(
    page_title="GDrive High-Speed Chunked Transfer",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for UI aesthetics
st.markdown("""
<style>
    /* Main Background & Fonts */
    .stApp {
        background-color: #0e1117;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    /* Card Container */
    .css-card {
        background: rgba(22, 27, 34, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        backdrop-filter: blur(10px);
    }
    
    /* Metric Card */
    .metric-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.7));
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #38bdf8;
    }
    .metric-label {
        font-size: 13px;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Buttons styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }

    /* Progress bar color */
    .stProgress > div > div > div > div {
        background-color: #38bdf8;
    }

    /* Header Accent */
    .header-accent {
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }
</style>
""", unsafe_allow_html=True)


def format_bytes(bytes_num: int) -> str:
    """Format byte size into human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_num) < 1024.0:
            return f"{bytes_num:3.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} PB"


def load_persistent_history():
    """Load completed transfer logs from disk."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_persistent_history(logs):
    """Save completed transfer logs to disk."""
    try:
        existing = load_persistent_history()
        existing.extend(logs)
        # Keep last 500 records
        existing = existing[-500:]
        with open(HISTORY_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        print(f"[App] Warning saving history log: {e}")


def on_subfolder_select_change(key_prefix: str):
    """Callback executed when user selects a subfolder from dropdown."""
    select_key = f"{key_prefix}_nav_select"
    selected = st.session_state.get(select_key)
    if selected and isinstance(selected, tuple) and selected[1] is not None:
        sub_folder = selected[1]
        sub_id = sub_folder['id']
        sub_name = sub_folder['name']
        st.session_state[f"{key_prefix}_gdrive_folder"] = (sub_id, sub_name)
        st.session_state[f"{key_prefix}_gdrive_history"].append((sub_id, sub_name))


def on_go_up_click(key_prefix: str):
    """Callback executed when user clicks Go Up button."""
    state_history_key = f"{key_prefix}_gdrive_history"
    state_folder_key = f"{key_prefix}_gdrive_folder"
    history = st.session_state.get(state_history_key, [])
    if len(history) > 1:
        history.pop()
        st.session_state[state_folder_key] = history[-1]


def on_jump_root_click(key_prefix: str):
    """Callback executed when user clicks Jump to Root button."""
    st.session_state[f"{key_prefix}_gdrive_history"] = [('root', 'My Drive (Root)')]
    st.session_state[f"{key_prefix}_gdrive_folder"] = ('root', 'My Drive (Root)')


def render_gdrive_folder_picker(key_prefix: str):
    """
    1-Click Native Callback Google Drive folder navigator component.
    """
    state_folder_key = f"{key_prefix}_gdrive_folder"
    state_history_key = f"{key_prefix}_gdrive_history"
    select_key = f"{key_prefix}_nav_select"

    if state_folder_key not in st.session_state:
        st.session_state[state_folder_key] = ('root', 'My Drive (Root)')
    if state_history_key not in st.session_state:
        st.session_state[state_history_key] = [('root', 'My Drive (Root)')]

    curr_id, curr_name = st.session_state[state_folder_key]
    history = st.session_state[state_history_key]

    path_names = [h[1] for h in history]
    st.info(f"📂 **Current GDrive Target Location:** `{' / '.join(path_names)}` (ID: `{curr_id}`)")

    try:
        items = st.session_state.connector.list_files(folder_id=curr_id)
    except Exception as e:
        st.error(f"Error loading GDrive folder: {e}")
        return curr_id, curr_name, []

    folders = [i for i in items if i['mimeType'] == 'application/vnd.google-apps.folder']
    files = [i for i in items if i['mimeType'] != 'application/vnd.google-apps.folder']

    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

    with btn_col1:
        if len(history) > 1:
            st.button(
                "⬅️ Go Up One Level",
                key=f"{key_prefix}_btn_up",
                on_click=on_go_up_click,
                args=(key_prefix,),
                use_container_width=True
            )

    with btn_col2:
        if len(history) > 1:
            st.button(
                "🏠 Jump to Root",
                key=f"{key_prefix}_btn_root",
                on_click=on_jump_root_click,
                args=(key_prefix,),
                use_container_width=True
            )

    with btn_col3:
        if st.button("🔄 Refresh Directory", key=f"{key_prefix}_btn_ref", use_container_width=True):
            st.rerun()

    if folders:
        options = [("-- Select subfolder to enter instantly --", None)] + [
            (f"📁 {f['name']}  [ID: {f['id'][:6]}]", f) for f in folders
        ]
        
        st.selectbox(
            "Subfolders in this directory:",
            options=options,
            format_func=lambda x: x[0],
            key=select_key,
            on_change=on_subfolder_select_change,
            args=(key_prefix,)
        )
    else:
        st.caption("No subfolders in this directory.")

    if files:
        with st.expander(f"📄 Files in '{curr_name}' ({len(files)} files)", expanded=False):
            df_files = pd.DataFrame([
                {'Name': f['name'], 'Size': format_bytes(int(f.get('size', 0))), 'ID': f['id']}
                for f in files
            ])
            st.dataframe(df_files, use_container_width=True)

    return curr_id, curr_name, items


def main():
    # Session State Initialization
    if 'connector' not in st.session_state:
        st.session_state.connector = GoogleDriveConnector()

    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated and os.path.exists('token.json'):
        try:
            if st.session_state.connector.authenticate():
                st.session_state.authenticated = True
        except Exception:
            st.session_state.authenticated = False

    # Sidebar Setup & Auth Status
    with st.sidebar:
        st.markdown("<h2 class='header-accent'>☁️ GDrive Transfer</h2>", unsafe_allow_html=True)
        st.markdown("Direct chunked streaming between Local PC/NAS & GDrive without temporary disk caching.")
        st.divider()

        st.markdown("### 🔐 Authentication Status")
        if st.session_state.authenticated:
            st.success("Connected to Google Drive")
            if st.button("Re-authenticate / Switch Account", use_container_width=True):
                if os.path.exists('token.json'):
                    os.remove('token.json')
                st.session_state.authenticated = False
                st.rerun()
        else:
            st.warning("Not Connected")
            if os.path.exists('credentials.json'):
                if st.button("🚀 Connect to Google Drive", type="primary", use_container_width=True):
                    with st.spinner("Opening login window in browser..."):
                        try:
                            st.session_state.connector.authenticate()
                            st.session_state.authenticated = True
                            st.success("Successfully logged in!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Login failed: {e}")
            else:
                st.error("Missing `credentials.json`!")
                st.info("Place your OAuth Client ID `credentials.json` file into the project folder to enable login.")

        st.divider()
        st.markdown("### ⚙️ Transfer Settings")

        skip_existing = st.checkbox(
            "⏩ Smart Resume: Skip already uploaded files",
            value=True,
            help="If checked, skips files that already exist on Google Drive with identical name and size."
        )

        chunk_size_mb = st.select_slider(
            "Streaming Chunk Size (RAM usage)",
            options=[8, 16, 32, 64],
            value=16,
            format_func=lambda x: f"{x} MB"
        )
        chunk_size_bytes = chunk_size_mb * 1024 * 1024

        st.caption(f"🚀 Single-threaded streaming with {chunk_size_mb}MB chunks.")

    # Main App Title
    st.markdown("<h1 class='header-accent'>Large File & NAS Transfer Studio</h1>", unsafe_allow_html=True)

    # Main Tab Selection
    tab_upload, tab_download, tab_history, tab_gdrive_browser = st.tabs([
        "⬆️ Upload (Local/NAS ➔ GDrive)",
        "⬇️ Download (GDrive ➔ Local/NAS)",
        "📜 Transfer Log History",
        "📁 Browse GDrive Folders"
    ])

    # ==============================================================================
    # TAB 1: UPLOAD (Local PC / NAS -> GDrive)
    # ==============================================================================
    with tab_upload:
        st.markdown("### 1. Select Local / NAS Folder or File")
        local_src_path = st.text_input(
            "Local PC or NAS Network Path (e.g. C:\\Data, D:\\Backup, \\\\192.168.1.50\\share\\files)",
            value="",
            placeholder="Enter absolute path or network UNC path...",
            key="upload_src_input"
        )

        valid_local_src = False
        folder_summary = None

        if local_src_path:
            norm_src = LocalNASFileManager.normalize_path(local_src_path)
            if LocalNASFileManager.path_exists(norm_src):
                valid_local_src = True
                is_folder = LocalNASFileManager.is_directory(norm_src)

                if is_folder:
                    st.success(f"Valid Directory: `{norm_src}`")
                    folder_summary = LocalNASFileManager.get_folder_summary(norm_src)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"<div class='metric-card'><div class='metric-value'>{folder_summary['total_files']}</div><div class='metric-label'>Total Files</div></div>", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"<div class='metric-card'><div class='metric-value'>{format_bytes(folder_summary['total_size'])}</div><div class='metric-label'>Total Size</div></div>", unsafe_allow_html=True)

                    with st.expander("📂 Folder File List Preview"):
                        files_preview = list(LocalNASFileManager.scan_folder_recursive(norm_src))
                        if files_preview:
                            df_prev = pd.DataFrame(files_preview)[['relative_path', 'size']]
                            df_prev['Size'] = df_prev['size'].apply(format_bytes)
                            st.dataframe(df_prev[['relative_path', 'Size']], use_container_width=True)
                else:
                    st.success(f"Valid File: `{norm_src}`")
                    f_size = os.path.getsize(norm_src)
                    st.markdown(f"<div class='metric-card'><div class='metric-value'>{format_bytes(f_size)}</div><div class='metric-label'>File Size</div></div>", unsafe_allow_html=True)
            else:
                st.error(f"Path does not exist or is inaccessible: `{norm_src}`")

        st.markdown("### 2. Destination GDrive Folder Selector")
        if st.session_state.authenticated:
            target_gdrive_id, target_gdrive_name, _ = render_gdrive_folder_picker("upload_dest")
            st.success(f"🎯 Target Upload Destination Folder: **{target_gdrive_name}** (ID: `{target_gdrive_id}`)")
        else:
            target_gdrive_id = 'root'
            target_gdrive_name = 'My Drive (Root)'
            st.warning("Please authenticate with Google Drive in the sidebar to browse folders.")

        st.markdown("---")
        
        # Upload Execution Button
        if valid_local_src and st.session_state.authenticated:
            if st.button("🚀 Start Chunked Streaming Upload", type="primary", use_container_width=True):
                st.markdown("### 📊 Live Transfer Progress")
                
                status_text = st.empty()
                overall_pbar = st.progress(0.0)
                file_pbar = st.progress(0.0)

                metric_col1, metric_col2, metric_col3 = st.columns(3)
                m_speed = metric_col1.empty()
                m_bytes = metric_col2.empty()
                m_file = metric_col3.empty()

                log_box = st.empty()
                logs = []

                norm_src = LocalNASFileManager.normalize_path(local_src_path)
                is_folder = LocalNASFileManager.is_directory(norm_src)

                if is_folder:
                    files_to_upload = list(LocalNASFileManager.scan_folder_recursive(norm_src))
                    total_batch_bytes = folder_summary['total_size'] if folder_summary else 1
                else:
                    files_to_upload = [{
                        'full_path': norm_src,
                        'relative_path': os.path.basename(norm_src),
                        'rel_dir_path': '',
                        'file_name': os.path.basename(norm_src),
                        'size': os.path.getsize(norm_src)
                    }]
                    total_batch_bytes = files_to_upload[0]['size']

                if not files_to_upload:
                    st.error(f"No files found to upload in path: `{norm_src}`")
                else:
                    completed_batch_bytes = 0
                    created_gdrive_folders = {}

                    for idx, item in enumerate(files_to_upload):
                        file_full_path = item['full_path']
                        file_rel_path = item['relative_path']
                        file_size = item['size']

                        m_file.metric("Current File", f"({idx+1}/{len(files_to_upload)}) {item['file_name']}")

                        # Determine target GDrive folder
                        target_id_for_item = target_gdrive_id
                        if is_folder and item.get('rel_dir_path'):
                            path_parts = item['rel_dir_path'].replace('\\', '/').split('/')
                            parent_id = target_gdrive_id
                            curr_path = ""

                            for part in path_parts:
                                curr_path = f"{curr_path}/{part}" if curr_path else part
                                if curr_path not in created_gdrive_folders:
                                    folder_id = st.session_state.connector.find_or_create_folder(part, parent_id=parent_id)
                                    created_gdrive_folders[curr_path] = folder_id
                                    parent_id = folder_id
                                else:
                                    parent_id = created_gdrive_folders[curr_path]
                            target_id_for_item = parent_id

                        # Check Smart Resume: Skip existing files
                        if skip_existing and st.session_state.connector.file_exists_in_folder(item['file_name'], file_size, parent_id=target_id_for_item):
                            completed_batch_bytes += file_size
                            batch_pct = (completed_batch_bytes / total_batch_bytes) if total_batch_bytes > 0 else 1.0
                            overall_pbar.progress(min(batch_pct, 1.0))
                            m_bytes.metric("Transferred", f"{format_bytes(completed_batch_bytes)} / {format_bytes(total_batch_bytes)}")

                            log_entry = {
                                'Time': time.strftime("%Y-%m-%d %H:%M:%S"),
                                'File': file_rel_path,
                                'Size': format_bytes(file_size),
                                'Status': '⏩ Skipped (Already Uploaded)',
                                'Duration': '0.0s'
                            }
                            logs.append(log_entry)
                            log_box.dataframe(pd.DataFrame(logs), use_container_width=True)
                            continue

                        def single_file_progress(uploaded, total, pct, speed_mbps):
                            nonlocal completed_batch_bytes
                            file_pbar.progress(min(pct / 100.0, 1.0))
                            current_batch = completed_batch_bytes + uploaded
                            batch_pct = (current_batch / total_batch_bytes) if total_batch_bytes > 0 else 1.0
                            overall_pbar.progress(min(batch_pct, 1.0))

                            m_speed.metric("Upload Speed", f"{speed_mbps:.2f} MB/s")
                            m_bytes.metric("Transferred", f"{format_bytes(current_batch)} / {format_bytes(total_batch_bytes)}")

                        status_text.markdown(f"**Uploading ({idx+1}/{len(files_to_upload)}):** `{file_rel_path}` ({format_bytes(file_size)})")
                        start_t = time.time()

                        try:
                            st.session_state.connector.upload_file(
                                local_path=file_full_path,
                                parent_id=target_id_for_item,
                                gdrive_file_name=item['file_name'],
                                chunk_size=chunk_size_bytes,
                                progress_callback=single_file_progress
                            )
                            elapsed = max(time.time() - start_t, 0.001)
                            completed_batch_bytes += file_size
                            log_entry = {
                                'Time': time.strftime("%Y-%m-%d %H:%M:%S"),
                                'File': file_rel_path,
                                'Size': format_bytes(file_size),
                                'Status': '✅ Success',
                                'Duration': f"{elapsed:.1f}s"
                            }
                            logs.append(log_entry)
                        except Exception as ex:
                            log_entry = {
                                'Time': time.strftime("%Y-%m-%d %H:%M:%S"),
                                'File': file_rel_path,
                                'Size': format_bytes(file_size),
                                'Status': f'❌ Failed ({ex})',
                                'Duration': 'N/A'
                            }
                            logs.append(log_entry)

                        log_box.dataframe(pd.DataFrame(logs), use_container_width=True)

                    save_persistent_history(logs)
                    status_text.success(f"🎉 Batch transfer complete! Processed {len(files_to_upload)} files.")
                    st.balloons()
        elif not st.session_state.authenticated:
            st.warning("Please authenticate with Google Drive in the sidebar first.")

    # ==============================================================================
    # TAB 2: DOWNLOAD (GDrive -> Local PC / NAS)
    # ==============================================================================
    with tab_download:
        st.markdown("### 1. Select Google Drive Source File or Folder")
        
        selected_gdrive_item = None

        if st.session_state.authenticated:
            curr_dl_folder_id, curr_dl_folder_name, folder_items = render_gdrive_folder_picker("download_dest")

            if folder_items:
                dl_select_key = "dl_item_select"
                item_options = [("-- Select a file or folder to download --", None)] + [
                    (f"{'📁 [FOLDER] ' if f['mimeType'] == 'application/vnd.google-apps.folder' else '📄 [FILE] '} {f['name']} ({format_bytes(int(f.get('size', 0))) if 'size' in f else 'Folder'}) [ID: {f['id'][:6]}]", f)
                    for f in folder_items
                ]
                selected_item_tuple = st.selectbox(
                    "Select Specific Item in This Folder to Download:",
                    options=item_options,
                    format_func=lambda x: x[0],
                    key=dl_select_key
                )
                if selected_item_tuple and selected_item_tuple[1] is not None:
                    selected_gdrive_item = selected_item_tuple[1]
                    st.info(f"Selected for Download: **{selected_gdrive_item['name']}** (ID: `{selected_gdrive_item['id']}`)")
            else:
                st.warning("Current directory has no files to download.")
        else:
            st.warning("Please authenticate in sidebar first.")

        st.markdown("### 2. Select Destination Local PC or NAS Directory")
        local_dest_dir = st.text_input(
            "Local or NAS Target Folder (e.g. C:\\Downloads, Z:\\NAS_Backup)",
            value="",
            placeholder="Enter destination directory path...",
            key="dl_dest_input"
        )

        valid_dest_dir = False
        if local_dest_dir:
            norm_dest = LocalNASFileManager.normalize_path(local_dest_dir)
            valid_dest_dir = True
            st.caption(f"Destination path: `{norm_dest}`")

        st.markdown("---")

        if selected_gdrive_item and valid_dest_dir and st.session_state.authenticated:
            if st.button("🚀 Start Chunked Streaming Download", type="primary", use_container_width=True):
                st.markdown("### 📊 Live Download Progress")

                status_text = st.empty()
                file_pbar = st.progress(0.0)

                metric_col1, metric_col2 = st.columns(2)
                m_speed = metric_col1.empty()
                m_bytes = metric_col2.empty()

                is_folder = selected_gdrive_item['mimeType'] == 'application/vnd.google-apps.folder'

                norm_dest = LocalNASFileManager.normalize_path(local_dest_dir)

                if not is_folder:
                    file_id = selected_gdrive_item['id']
                    file_name = selected_gdrive_item['name']
                    file_size = int(selected_gdrive_item.get('size', 0))
                    target_path = os.path.join(norm_dest, file_name)

                    status_text.markdown(f"**Downloading:** `{file_name}` ({format_bytes(file_size)}) directly to `{target_path}`")

                    def dl_progress_cb(dl_bytes, total, pct, speed_mbps):
                        file_pbar.progress(min(pct / 100.0, 1.0))
                        m_speed.metric("Download Speed", f"{speed_mbps:.2f} MB/s")
                        m_bytes.metric("Downloaded", f"{format_bytes(dl_bytes)} / {format_bytes(total)}")

                    try:
                        start_t = time.time()
                        st.session_state.connector.download_file(
                            file_id=file_id,
                            local_destination_path=target_path,
                            chunk_size=chunk_size_bytes,
                            progress_callback=dl_progress_cb
                        )
                        elapsed = max(time.time() - start_t, 0.001)
                        status_text.success(f"🎉 Download complete! Saved to `{target_path}` ({elapsed:.1f}s)")
                        st.balloons()
                    except Exception as ex:
                        st.error(f"Download failed: {ex}")
                else:
                    st.warning("Downloading folder contents...")
                    def download_gdrive_folder_recursive(folder_id, local_target_dir):
                        g_files = st.session_state.connector.list_files(folder_id=folder_id)
                        for gf in g_files:
                            if gf['mimeType'] == 'application/vnd.google-apps.folder':
                                sub_dir = os.path.join(local_target_dir, gf['name'])
                                os.makedirs(sub_dir, exist_ok=True)
                                download_gdrive_folder_recursive(gf['id'], sub_dir)
                            else:
                                f_path = os.path.join(local_target_dir, gf['name'])
                                st.session_state.connector.download_file(
                                    file_id=gf['id'],
                                    local_destination_path=f_path,
                                    chunk_size=chunk_size_bytes
                                )

                    with st.spinner("Downloading folder contents..."):
                        try:
                            target_subfolder = os.path.join(norm_dest, selected_gdrive_item['name'])
                            download_gdrive_folder_recursive(selected_gdrive_item['id'], target_subfolder)
                            status_text.success(f"🎉 Folder downloaded to `{target_subfolder}`")
                            st.balloons()
                        except Exception as ex:
                            st.error(f"Folder download failed: {ex}")

    # ==============================================================================
    # TAB 3: PERSISTENT TRANSFER HISTORY
    # ==============================================================================
    with tab_history:
        st.markdown("### 📜 Transfer History Log")
        history_data = load_persistent_history()
        if history_data:
            df_hist = pd.DataFrame(history_data)
            st.dataframe(df_hist, use_container_width=True)
            if st.button("🗑️ Clear Log History"):
                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)
                st.rerun()
        else:
            st.info("No saved transfer history found yet.")

    # ==============================================================================
    # TAB 4: BROWSE GDRIVE FOLDERS
    # ==============================================================================
    with tab_gdrive_browser:
        st.markdown("### 📁 Google Drive Explorer")
        if not st.session_state.authenticated:
            st.warning("Please connect to Google Drive in the sidebar first.")
        else:
            render_gdrive_folder_picker("full_explorer")

if __name__ == '__main__':
    main()
