import os
import io
import time
from typing import Callable, Optional, List, Dict, Any
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']
DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024


class GoogleDriveConnector:
    """
    Single-Threaded Google Drive API Connector with Auto-Token Refreshing,
    Resumable Streaming, and Smart Duplicate File Detection.
    """

    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds: Optional[Credentials] = None
        self.service = None
        self.http_session = requests.Session()

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3
        )
        self.http_session.mount('https://', adapter)
        self.http_session.mount('http://', adapter)

    def authenticate(self, port: int = 0) -> bool:
        """Authenticate using credentials.json or saved token.json."""
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                print(f"[GDrive] Warning: Could not load token file: {e}")
                self.creds = None

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"[GDrive] Token refresh failed: {e}. Re-authenticating...")
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"OAuth Credentials file not found at '{self.credentials_path}'."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=port)

            with open(self.token_path, 'w') as token_file:
                token_file.write(self.creds.to_json())

        self.service = build('drive', 'v3', credentials=self.creds)
        print("[GDrive] Authentication successful.")
        return True

    def _ensure_token_valid(self):
        """Auto-refresh access token if expired before API requests."""
        if not self.creds:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        if self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                with open(self.token_path, 'w') as token_file:
                    token_file.write(self.creds.to_json())
                print("[GDrive] Token auto-refreshed successfully.")
            except Exception as e:
                print(f"[GDrive] Warning: Auto-token refresh failed: {e}")

    def get_auth_headers(self) -> Dict[str, str]:
        """Get bearer authorization header with active token."""
        self._ensure_token_valid()
        return {'Authorization': f'Bearer {self.creds.token}'}

    def _execute_with_retry(self, action_func, max_retries: int = 3):
        """Execute Google Drive action with automatic retry for connection issues."""
        for attempt in range(max_retries):
            try:
                self._ensure_token_valid()
                return action_func()
            except (requests.exceptions.RequestException, OSError, Exception) as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5 * (attempt + 1))

    def list_files(
        self,
        folder_id: str = 'root',
        page_size: int = 100,
        query_extra: str = ""
    ) -> List[Dict[str, Any]]:
        """List files inside a folder."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        query = f"'{folder_id}' in parents and trashed = false"
        if query_extra:
            query += f" and ({query_extra})"

        def _do_list():
            files = []
            page_token = None
            while True:
                response = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                    pageToken=page_token,
                    pageSize=page_size
                ).execute()

                files.extend(response.get('files', []))
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            return files

        return self._execute_with_retry(_do_list)

    def file_exists_in_folder(self, filename: str, file_size: int, parent_id: str = 'root') -> bool:
        """
        Check if a file with the exact name and size already exists in target GDrive folder.
        """
        try:
            # Escape single quotes in filename for drive query
            safe_name = filename.replace("'", "\\'")
            query = f"name = '{safe_name}' and size = {file_size}"
            matches = self.list_files(folder_id=parent_id, query_extra=query)
            return len(matches) > 0
        except Exception as e:
            print(f"[GDrive] Warning checking file existence: {e}")
            return False

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Fetch metadata for a file."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        def _do_get():
            return self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, modifiedTime, parents'
            ).execute()

        return self._execute_with_retry(_do_get)

    def create_folder(self, folder_name: str, parent_id: str = 'root') -> str:
        """Create a new folder in Google Drive."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        def _do_create():
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            return folder.get('id')

        return self._execute_with_retry(_do_create)

    def find_or_create_folder(self, folder_name: str, parent_id: str = 'root') -> str:
        """Find an existing subfolder by name or create it if missing."""
        existing = self.list_files(
            folder_id=parent_id,
            query_extra=f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
        )
        if existing:
            return existing[0]['id']
        return self.create_folder(folder_name, parent_id=parent_id)

    def upload_file(
        self,
        local_path: str,
        parent_id: str = 'root',
        gdrive_file_name: Optional[str] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        progress_callback: Optional[Callable[[int, int, float, float], None]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file using sequential chunked streaming directly over HTTP.
        Auto-refreshes token mid-upload if transfer runs over 1 hour.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Source file not found: {local_path}")

        file_size = os.path.getsize(local_path)
        filename = gdrive_file_name or os.path.basename(local_path)

        # Ensure active token before starting session
        self._ensure_token_valid()

        # 1. Initiate Resumable Upload Session
        init_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
        headers = self.get_auth_headers()
        headers['Content-Type'] = 'application/json; charset=UTF-8'
        headers['X-Upload-Content-Length'] = str(file_size)

        metadata = {'name': filename, 'parents': [parent_id]}

        init_resp = self.http_session.post(init_url, headers=headers, json=metadata)
        if init_resp.status_code != 200:
            raise RuntimeError(f"Failed to initiate upload session: {init_resp.status_code} {init_resp.text}")

        upload_url = init_resp.headers.get('Location')
        if not upload_url:
            raise RuntimeError("Resumable upload URL missing in response headers.")

        chunk_size = max(262144, (chunk_size // 262144) * 262144)

        if file_size == 0:
            resp = self.http_session.put(
                upload_url,
                headers={'Content-Length': '0', 'Content-Range': 'bytes */0'}
            )
            return resp.json() if resp.status_code in (200, 201) else {'name': filename, 'size': 0}

        bytes_uploaded = 0
        start_time = time.time()
        last_time = start_time
        last_bytes = 0

        with open(local_path, 'rb') as f:
            while bytes_uploaded < file_size:
                # Keep token active during long multi-hour uploads
                self._ensure_token_valid()

                chunk_data = f.read(chunk_size)
                if not chunk_data:
                    break

                chunk_len = len(chunk_data)
                start_byte = bytes_uploaded
                end_byte = bytes_uploaded + chunk_len - 1

                put_headers = {
                    'Content-Length': str(chunk_len),
                    'Content-Range': f"bytes {start_byte}-{end_byte}/{file_size}"
                }

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        resp = self.http_session.put(upload_url, headers=put_headers, data=chunk_data)
                        if resp.status_code in (200, 201):
                            bytes_uploaded += chunk_len
                            now = time.time()
                            if progress_callback:
                                speed_mbps = (chunk_len / (1024 * 1024)) / max(now - last_time, 0.001)
                                pct = (bytes_uploaded / file_size) * 100.0 if file_size > 0 else 100.0
                                progress_callback(bytes_uploaded, file_size, pct, speed_mbps)
                            return resp.json()
                        elif resp.status_code == 308:
                            bytes_uploaded += chunk_len
                            now = time.time()
                            if progress_callback:
                                speed_mbps = (chunk_len / (1024 * 1024)) / max(now - last_time, 0.001)
                                pct = (bytes_uploaded / file_size) * 100.0 if file_size > 0 else 0.0
                                progress_callback(bytes_uploaded, file_size, pct, speed_mbps)
                            last_time = now
                            break
                        else:
                            if attempt == max_retries - 1:
                                raise RuntimeError(f"Chunk upload error {resp.status_code}: {resp.text}")
                            time.sleep(1)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise e
                        time.sleep(1)

        total_elapsed = max(time.time() - start_time, 0.001)
        overall_speed = (file_size / (1024 * 1024)) / total_elapsed
        if progress_callback:
            progress_callback(file_size, file_size, 100.0, overall_speed)

        return {'name': filename, 'size': file_size}

    def download_file(
        self,
        file_id: str,
        local_destination_path: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        progress_callback: Optional[Callable[[int, int, float, float], None]] = None
    ) -> str:
        """Download a file with streaming socket buffers."""
        metadata = self.get_file_metadata(file_id)
        total_bytes = int(metadata.get('size', 0))

        os.makedirs(os.path.dirname(os.path.abspath(local_destination_path)), exist_ok=True)

        download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        headers = self.get_auth_headers()

        resp = self.http_session.get(download_url, headers=headers, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(f"Download failed: {resp.status_code} {resp.text}")

        bytes_downloaded = 0
        start_time = time.time()
        last_time = start_time
        last_bytes = 0

        buffer_slice_size = 4 * 1024 * 1024

        with open(local_destination_path, 'wb') as fh:
            for chunk in resp.iter_content(chunk_size=buffer_slice_size):
                if chunk:
                    fh.write(chunk)
                    bytes_downloaded += len(chunk)
                    now = time.time()

                    if progress_callback and (bytes_downloaded - last_bytes >= 8 * 1024 * 1024 or bytes_downloaded == total_bytes):
                        elapsed_period = max(now - last_time, 0.001)
                        period_bytes = bytes_downloaded - last_bytes
                        speed_mbps = (period_bytes / (1024 * 1024)) / elapsed_period
                        pct = (bytes_downloaded / total_bytes) * 100.0 if total_bytes > 0 else 0.0
                        progress_callback(bytes_downloaded, total_bytes, pct, speed_mbps)
                        last_time = now
                        last_bytes = bytes_downloaded

        total_elapsed = max(time.time() - start_time, 0.001)
        overall_speed = (total_bytes / (1024 * 1024)) / total_elapsed
        if progress_callback:
            progress_callback(total_bytes, total_bytes, 100.0, overall_speed)

        return local_destination_path
