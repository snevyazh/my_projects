import os
import glob
from typing import List, Dict, Any, Generator, Tuple

class LocalNASFileManager:
    """
    Helper for interacting with Local PC file system and Network Drives / NAS paths
    (e.g., C:\\..., Z:\\..., \\\\NAS\\share\\...).
    """

    @staticmethod
    def normalize_path(path_str: str) -> str:
        """Normalize windows/UNC paths."""
        path_str = path_str.strip().strip('"').strip("'")
        return os.path.normpath(path_str)

    @staticmethod
    def path_exists(path_str: str) -> bool:
        """Check if local or UNC network path exists."""
        norm_path = LocalNASFileManager.normalize_path(path_str)
        return os.path.exists(norm_path)

    @staticmethod
    def is_directory(path_str: str) -> bool:
        """Check if path is a directory."""
        norm_path = LocalNASFileManager.normalize_path(path_str)
        return os.path.isdir(norm_path)

    @staticmethod
    def is_file(path_str: str) -> bool:
        """Check if path is a regular file."""
        norm_path = LocalNASFileManager.normalize_path(path_str)
        return os.path.isfile(norm_path)

    @staticmethod
    def list_directory(dir_path: str) -> List[Dict[str, Any]]:
        """
        List items in a directory (local or network drive).
        Returns a list of dicts with name, full_path, is_dir, size, modified_time.
        """
        norm_path = LocalNASFileManager.normalize_path(dir_path)
        if not os.path.exists(norm_path) or not os.path.isdir(norm_path):
            raise ValueError(f"Directory does not exist or is not a folder: {dir_path}")

        items = []
        try:
            with os.scandir(norm_path) as entries:
                for entry in entries:
                    try:
                        stat = entry.stat()
                        items.append({
                            'name': entry.name,
                            'full_path': entry.path,
                            'is_dir': entry.is_dir(),
                            'size': stat.st_size if not entry.is_dir() else 0,
                            'modified_time': stat.st_mtime
                        })
                    except OSError as e:
                        # Skip unaccessible files (permission errors)
                        print(f"[FileManager] Skipping '{entry.name}': {e}")
        except PermissionError as pe:
            raise PermissionError(f"Access denied to folder: {dir_path}")

        # Sort: directories first, then files alphabetically
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return items

    @staticmethod
    def scan_folder_recursive(dir_path: str) -> Generator[Dict[str, Any], None, None]:
        """
        Recursively scan a directory tree on local/NAS disk.
        Yields dict for each file found:
        {
            'full_path': str,
            'relative_path': str,
            'size': int,
            'rel_dir': str  (relative directory path for folder hierarchy creation)
        }
        """
        norm_path = LocalNASFileManager.normalize_path(dir_path)
        if not os.path.exists(norm_path):
            return

        base_dir_name = os.path.basename(norm_path)

        for root, dirs, files in os.walk(norm_path):
            for file_name in files:
                full_file_path = os.path.join(root, file_name)
                try:
                    size = os.path.getsize(full_file_path)
                except OSError:
                    size = 0

                # Relative path inside the root folder being scanned
                rel_path = os.path.relpath(full_file_path, norm_path)
                rel_dir = os.path.dirname(rel_path)
                if rel_dir == '.':
                    rel_dir = ""

                yield {
                    'full_path': full_file_path,
                    'relative_path': os.path.join(base_dir_name, rel_path),
                    'rel_dir_path': os.path.join(base_dir_name, rel_dir) if rel_dir else base_dir_name,
                    'file_name': file_name,
                    'size': size
                }

    @staticmethod
    def get_folder_summary(dir_path: str) -> Dict[str, Any]:
        """
        Calculate total file count and total size in bytes for a local/NAS folder.
        """
        norm_path = LocalNASFileManager.normalize_path(dir_path)
        total_files = 0
        total_size = 0

        if not os.path.exists(norm_path):
            return {'total_files': 0, 'total_size': 0}

        if os.path.isfile(norm_path):
            return {'total_files': 1, 'total_size': os.path.getsize(norm_path)}

        for item in LocalNASFileManager.scan_folder_recursive(norm_path):
            total_files += 1
            total_size += item['size']

        return {
            'total_files': total_files,
            'total_size': total_size
        }
