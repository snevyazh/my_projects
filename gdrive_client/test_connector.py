import os
import sys
import time
from tqdm import tqdm
from gdrive_connector import GoogleDriveConnector

def format_bytes(bytes_num: int) -> str:
    """Format bytes to human readable string (KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_num) < 1024.0:
            return f"{bytes_num:3.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} PB"


def main():
    print("=" * 60)
    print(" Google Drive Chunked Streaming Connector Test ")
    print("=" * 60)

    creds_file = 'credentials.json'
    token_file = 'token.json'

    if not os.path.exists(creds_file) and not os.path.exists(token_file):
        print(f"\n[!] WARNING: '{creds_file}' was not found in current directory.")
        print("    To authenticate, please download your Google OAuth Client ID JSON from")
        print("    Google Cloud Console and save it as 'credentials.json' in this folder:\n")
        print(f"    Target path: {os.path.abspath(creds_file)}\n")
        print("    Once 'credentials.json' is present, run this script again.")
        sys.exit(1)

    connector = GoogleDriveConnector(credentials_path=creds_file, token_path=token_file)

    try:
        print("\n[1/4] Authenticating with Google Drive...")
        connector.authenticate()
        print("[✓] Authenticated successfully!")
    except Exception as e:
        print(f"[X] Authentication failed: {e}")
        sys.exit(1)

    print("\n[2/4] Listing top 10 items in Root folder...")
    try:
        files = connector.list_files(folder_id='root', page_size=10)
        print(f"Found {len(files)} items:")
        for f in files:
            is_folder = f.get('mimeType') == 'application/vnd.google-apps.folder'
            item_type = "[FOLDER]" if is_folder else "[FILE]  "
            size_str = format_bytes(int(f.get('size', 0))) if 'size' in f else "N/A"
            print(f"  {item_type} {f.get('name'):<35} (ID: {f.get('id')}, Size: {size_str})")
    except Exception as e:
        print(f"[X] Failed to list files: {e}")
        sys.exit(1)

    # Ask user or test streaming upload/download
    print("\n[3/4] Testing Chunked Streaming Upload (Creating 50MB temporary test file)...")
    test_file_path = "test_50mb_file.bin"
    file_size_mb = 50
    file_size_bytes = file_size_mb * 1024 * 1024

    print(f"Generating synthetic {file_size_mb} MB test file directly on disk...")
    with open(test_file_path, "wb") as f:
        # Write chunks to avoid allocating 50MB in memory at once
        chunk = b"0" * (1024 * 1024)
        for _ in range(file_size_mb):
            f.write(chunk)

    pbar = None

    def upload_progress(bytes_uploaded, total_bytes, percent, speed_mbps):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total_bytes, unit='B', unit_scale=True, desc="Uploading to GDrive")
        pbar.n = bytes_uploaded
        pbar.set_postfix({'speed': f"{speed_mbps:.2f} MB/s", 'pct': f"{percent:.1f}%"})
        pbar.refresh()

    try:
        print(f"Uploading '{test_file_path}' (Direct chunk size: 8MB)...")
        uploaded_file = connector.upload_file(
            local_path=test_file_path,
            parent_id='root',
            chunk_size=8 * 1024 * 1024,
            progress_callback=upload_progress
        )
        if pbar:
            pbar.close()
        print(f"\n[✓] Upload completed! Remote File ID: {uploaded_file.get('id')}")

        uploaded_id = uploaded_file.get('id')

        print("\n[4/4] Testing Chunked Streaming Download...")
        download_target_path = "test_50mb_downloaded.bin"
        if os.path.exists(download_target_path):
            os.remove(download_target_path)

        pbar_dl = None

        def download_progress(bytes_dl, total_bytes, percent, speed_mbps):
            nonlocal pbar_dl
            if pbar_dl is None:
                pbar_dl = tqdm(total=total_bytes, unit='B', unit_scale=True, desc="Downloading from GDrive")
            pbar_dl.n = bytes_dl
            pbar_dl.set_postfix({'speed': f"{speed_mbps:.2f} MB/s", 'pct': f"{percent:.1f}%"})
            pbar_dl.refresh()

        connector.download_file(
            file_id=uploaded_id,
            local_destination_path=download_target_path,
            chunk_size=8 * 1024 * 1024,
            progress_callback=download_progress
        )
        if pbar_dl:
            pbar_dl.close()

        print(f"\n[✓] Download completed to '{download_target_path}'!")

        # Verify size match
        dl_size = os.path.getsize(download_target_path)
        if dl_size == file_size_bytes:
            print(f"[✓] VERIFICATION SUCCESS: Downloaded file size matches perfectly ({format_bytes(dl_size)})!")
        else:
            print(f"[!] Mismatch: Expected {file_size_bytes} bytes, got {dl_size} bytes.")

        # Cleanup local test files
        print("\nCleaning up local test files...")
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        if os.path.exists(download_target_path):
            os.remove(download_target_path)

        # Cleanup GDrive test file
        print(f"Deleting test file {uploaded_id} from GDrive...")
        connector.service.files().delete(fileId=uploaded_id).execute()
        print("[✓] Cleaned up remote test file.")

    except Exception as e:
        print(f"\n[X] Test failed: {e}")
    finally:
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        if os.path.exists(download_target_path):
            os.remove(download_target_path)

    print("\n" + "=" * 60)
    print(" Step 1 Connector Test Finished ")
    print("=" * 60)

if __name__ == '__main__':
    main()
