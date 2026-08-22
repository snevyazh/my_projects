from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Protocol

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

ProgressCallback = Callable[[int, int], None]
FolderProgressCallback = Callable[[dict], None]


class CancelToken(Protocol):
    def is_set(self) -> bool:
        ...


class TransferCancelled(Exception):
    """Raised when cancellation is requested."""


@dataclass
class ObjectInfo:
    key: str
    size: int
    last_modified: object | None = None


class _TransferProgress:
    def __init__(
        self,
        total_bytes: int,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        self.total_bytes = max(int(total_bytes), 0)
        self.callback = callback
        self.cancel_token = cancel_token
        self.transferred = 0

    def __call__(self, bytes_amount: int):
        if self.cancel_token and self.cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")

        self.transferred += int(bytes_amount)

        if self.callback:
            self.callback(
                min(self.transferred, self.total_bytes),
                self.total_bytes,
            )

        if self.cancel_token and self.cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")


class B2Backend:
    def __init__(self):
        endpoint = os.getenv("B2_ENDPOINT", "").strip()
        bucket = os.getenv("B2_BUCKET", "").strip()
        key_id = os.getenv("B2_KEY_ID", "").strip()
        app_key = os.getenv("B2_APPLICATION_KEY", "").strip()

        missing = [
            name
            for name, value in {
                "B2_ENDPOINT": endpoint,
                "B2_BUCKET": bucket,
                "B2_KEY_ID": key_id,
                "B2_APPLICATION_KEY": app_key,
            }.items()
            if not value
        ]

        if missing:
            raise RuntimeError("Missing env vars: " + ", ".join(missing))

        self.bucket = bucket

        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 10, "mode": "adaptive"},
                connect_timeout=30,
                read_timeout=300,
            ),
        )

        # Single-threaded boto3 transfer. The whole transfer itself may run
        # in a separate worker PROCESS, but boto3 never shares a client
        # across threads/processes.
        self.transfer_config = TransferConfig(
            multipart_threshold=64 * 1024 * 1024,
            multipart_chunksize=64 * 1024 * 1024,
            max_concurrency=1,
            use_threads=False,
        )

    def test_connection(self):
        return self.s3.head_bucket(Bucket=self.bucket)

    def list_folder(
        self,
        prefix: str = "",
    ) -> tuple[list[str], list[ObjectInfo]]:
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        folders: list[str] = []
        files: list[ObjectInfo] = []

        paginator = self.s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
            Delimiter="/",
        ):
            for common_prefix in page.get("CommonPrefixes", []):
                folders.append(common_prefix["Prefix"])

            for obj in page.get("Contents", []):
                key = obj["Key"]

                if key == prefix:
                    continue

                files.append(
                    ObjectInfo(
                        key=key,
                        size=int(obj.get("Size", 0)),
                        last_modified=obj.get("LastModified"),
                    )
                )

        return (
            sorted(folders),
            sorted(files, key=lambda item: item.key.lower()),
        )

    def iter_objects(
        self,
        prefix: str = "",
    ) -> Iterator[ObjectInfo]:
        paginator = self.s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
        ):
            for obj in page.get("Contents", []):
                yield ObjectInfo(
                    key=obj["Key"],
                    size=int(obj.get("Size", 0)),
                    last_modified=obj.get("LastModified"),
                )

    def get_prefix_stats(
        self,
        prefix: str = "",
    ) -> dict:
        """
        Return recursive totals for a prefix plus recursive totals for each
        immediate child folder.

        Example at bucket root:
            Foreign/ -> total bytes of everything below Foreign/
            Israel/  -> total bytes of everything below Israel/

        This requires one recursive ListObjectsV2 scan under `prefix`.
        """
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        total_size = 0
        total_objects = 0
        child_folders: dict[str, dict[str, int]] = {}

        for obj in self.iter_objects(prefix):
            key = obj.key

            if key == prefix:
                continue

            relative = key[len(prefix):] if prefix else key

            # Ignore empty folder markers if any exist.
            if relative == "":
                continue

            total_size += obj.size
            total_objects += 1

            if "/" in relative:
                child_name = relative.split("/", 1)[0]
                child_prefix = f"{prefix}{child_name}/"

                stats = child_folders.setdefault(
                    child_prefix,
                    {
                        "size": 0,
                        "objects": 0,
                    },
                )

                stats["size"] += obj.size
                stats["objects"] += 1

        return {
            "size": total_size,
            "objects": total_objects,
            "child_folders": child_folders,
        }

    def head_object(self, key: str):
        return self.s3.head_object(
            Bucket=self.bucket,
            Key=key,
        )

    def upload_file(
        self,
        local_path: str | Path,
        key: str,
        progress_callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        local_path = Path(local_path)

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")

        total_bytes = local_path.stat().st_size

        callback = _TransferProgress(
            total_bytes=total_bytes,
            callback=progress_callback,
            cancel_token=cancel_token,
        )

        self.s3.upload_file(
            str(local_path),
            self.bucket,
            key,
            Config=self.transfer_config,
            Callback=callback,
        )

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")

    def download_file(
        self,
        key: str,
        local_path: str | Path,
        progress_callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")

        meta = self.head_object(key)
        total_bytes = int(meta["ContentLength"])

        callback = _TransferProgress(
            total_bytes=total_bytes,
            callback=progress_callback,
            cancel_token=cancel_token,
        )

        self.s3.download_file(
            self.bucket,
            key,
            str(local_path),
            Config=self.transfer_config,
            Callback=callback,
        )

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Transfer cancelled by user.")

    def delete_file(self, key: str):
        self.s3.delete_object(
            Bucket=self.bucket,
            Key=key,
        )

    def copy_object(
        self,
        source_key: str,
        destination_key: str,
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        source_key = source_key.strip("/")
        destination_key = destination_key.strip("/")

        if not source_key or not destination_key:
            raise ValueError("Source and destination object keys are required.")

        if source_key == destination_key:
            raise ValueError("Source and destination object keys must differ.")

        if not overwrite:
            try:
                self.head_object(destination_key)
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code", "")

                if code not in {"404", "NotFound", "NoSuchKey"}:
                    raise
            else:
                raise FileExistsError(
                    f"Destination object already exists: {destination_key}"
                )

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Copy cancelled by user.")

        meta = self.head_object(source_key)
        total_bytes = int(meta["ContentLength"])
        callback = _TransferProgress(
            total_bytes=total_bytes,
            callback=progress_callback,
            cancel_token=cancel_token,
        )

        # boto3's managed copy automatically switches to multipart copy for
        # objects above the configured threshold.
        self.s3.copy(
            {
                "Bucket": self.bucket,
                "Key": source_key,
            },
            self.bucket,
            destination_key,
            Config=self.transfer_config,
            Callback=callback,
        )

        if cancel_token and cancel_token.is_set():
            raise TransferCancelled("Copy cancelled by user.")

        return total_bytes

    def copy_folder(
        self,
        source_prefix: str,
        destination_prefix: str,
        move: bool = False,
        overwrite: bool = False,
        progress_callback: FolderProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        source_prefix = source_prefix.strip("/")
        destination_prefix = destination_prefix.strip("/")

        if not source_prefix or not destination_prefix:
            raise ValueError("Source and destination prefixes are required.")

        if source_prefix == destination_prefix:
            raise ValueError("Source and destination prefixes must differ.")

        source_root = source_prefix + "/"
        destination_root = destination_prefix + "/"

        if (
            destination_root.startswith(source_root)
            or source_root.startswith(destination_root)
        ):
            raise ValueError(
                "Source and destination prefixes cannot contain one another."
            )

        objects = [
            obj
            for obj in self.iter_objects(source_root)
            if obj.key != source_root
            and not (obj.key.endswith("/") and obj.size == 0)
        ]

        if not objects:
            raise ValueError(f"No objects found under prefix: {source_root}")

        total_files = len(objects)
        total_bytes = sum(obj.size for obj in objects)
        processed_files = 0
        processed_bytes = 0
        copied = 0
        deleted = 0
        failed: list[tuple[str, str]] = []

        def emit(
            *,
            current_file: str = "",
            current_bytes: int = 0,
            current_size: int = 0,
            status: str = "running",
        ):
            if progress_callback:
                progress_callback(
                    {
                        "status": status,
                        "total_files": total_files,
                        "processed_files": processed_files,
                        "total_bytes": total_bytes,
                        "processed_bytes": processed_bytes,
                        "current_file": current_file,
                        "current_bytes": current_bytes,
                        "current_size": current_size,
                        "copied": copied,
                        "deleted": deleted,
                        "failed": len(failed),
                    }
                )

        emit()

        for obj in objects:
            if cancel_token and cancel_token.is_set():
                emit(status="cancelled")
                raise TransferCancelled("Folder copy cancelled by user.")

            relative = obj.key[len(source_root):]
            destination_key = destination_root + relative
            file_transferred = 0

            def on_file_progress(transferred: int, file_total: int):
                nonlocal file_transferred
                file_transferred = transferred

                if progress_callback:
                    progress_callback(
                        {
                            "status": "running",
                            "total_files": total_files,
                            "processed_files": processed_files,
                            "total_bytes": total_bytes,
                            "processed_bytes": processed_bytes + transferred,
                            "current_file": relative,
                            "current_bytes": transferred,
                            "current_size": file_total,
                            "copied": copied,
                            "deleted": deleted,
                            "failed": len(failed),
                        }
                    )

            try:
                self.copy_object(
                    obj.key,
                    destination_key,
                    overwrite=overwrite,
                    progress_callback=on_file_progress,
                    cancel_token=cancel_token,
                )
                copied += 1
                processed_files += 1
                processed_bytes += obj.size
                emit(
                    current_file=relative,
                    current_bytes=obj.size,
                    current_size=obj.size,
                )

            except TransferCancelled:
                emit(
                    current_file=relative,
                    current_bytes=file_transferred,
                    current_size=obj.size,
                    status="cancelled",
                )
                raise

            except Exception as error:
                failed.append((obj.key, repr(error)))
                processed_files += 1
                emit(
                    current_file=relative,
                    current_bytes=file_transferred,
                    current_size=obj.size,
                )

        # A folder move deletes nothing unless every copy succeeded. This
        # avoids losing source objects during a partially successful batch.
        if move and not failed:
            emit(status="deleting")

            for obj in objects:
                if cancel_token and cancel_token.is_set():
                    emit(status="cancelled")
                    raise TransferCancelled("Folder move cancelled by user.")

                try:
                    self.delete_file(obj.key)
                    deleted += 1
                    emit(status="deleting")
                except Exception as error:
                    failed.append((obj.key, repr(error)))
                    emit(status="deleting")

        emit(status="complete" if not failed else "completed_with_errors")

        return {
            "copied": copied,
            "deleted": deleted,
            "failed": failed,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "processed_bytes": processed_bytes,
        }

    def upload_folder(
        self,
        local_folder: str | Path,
        remote_prefix: str = "",
        skip_same_size: bool = True,
        progress_callback: FolderProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ):
        local_folder = Path(local_folder).resolve()

        if not local_folder.is_dir():
            raise ValueError(f"Not a folder: {local_folder}")

        remote_prefix = remote_prefix.strip("/")

        files = [
            path
            for path in local_folder.rglob("*")
            if path.is_file()
        ]

        total_files = len(files)
        total_bytes = sum(path.stat().st_size for path in files)

        uploaded = 0
        skipped = 0
        failed: list[tuple[str, str]] = []
        processed_files = 0
        processed_bytes = 0

        def emit(
            *,
            current_file: str = "",
            current_bytes: int = 0,
            current_size: int = 0,
            status: str = "running",
        ):
            if progress_callback:
                progress_callback(
                    {
                        "status": status,
                        "total_files": total_files,
                        "processed_files": processed_files,
                        "total_bytes": total_bytes,
                        "processed_bytes": processed_bytes,
                        "current_file": current_file,
                        "current_bytes": current_bytes,
                        "current_size": current_size,
                        "uploaded": uploaded,
                        "skipped": skipped,
                        "failed": len(failed),
                    }
                )

        emit()

        for path in files:
            if cancel_token and cancel_token.is_set():
                emit(status="cancelled")
                raise TransferCancelled("Folder upload cancelled by user.")

            rel = path.relative_to(local_folder).as_posix()
            key = f"{remote_prefix}/{rel}" if remote_prefix else rel
            size = path.stat().st_size

            if skip_same_size:
                try:
                    meta = self.head_object(key)

                    if int(meta["ContentLength"]) == size:
                        skipped += 1
                        processed_files += 1
                        processed_bytes += size

                        emit(
                            current_file=rel,
                            current_bytes=size,
                            current_size=size,
                        )
                        continue

                except ClientError as error:
                    code = (
                        error.response
                        .get("Error", {})
                        .get("Code", "")
                    )

                    if code not in {"404", "NotFound", "NoSuchKey"}:
                        failed.append((str(path), str(error)))
                        processed_files += 1
                        emit(
                            current_file=rel,
                            current_bytes=0,
                            current_size=size,
                        )
                        continue

            file_transferred = 0

            def on_file_progress(
                transferred: int,
                file_total: int,
            ):
                nonlocal file_transferred
                file_transferred = transferred

                if cancel_token and cancel_token.is_set():
                    raise TransferCancelled(
                        "Folder upload cancelled by user."
                    )

                if progress_callback:
                    progress_callback(
                        {
                            "status": "running",
                            "total_files": total_files,
                            "processed_files": processed_files,
                            "total_bytes": total_bytes,
                            "processed_bytes": processed_bytes + transferred,
                            "current_file": rel,
                            "current_bytes": transferred,
                            "current_size": file_total,
                            "uploaded": uploaded,
                            "skipped": skipped,
                            "failed": len(failed),
                        }
                    )

            try:
                self.upload_file(
                    path,
                    key,
                    progress_callback=on_file_progress,
                    cancel_token=cancel_token,
                )

                uploaded += 1
                processed_files += 1
                processed_bytes += size

                emit(
                    current_file=rel,
                    current_bytes=size,
                    current_size=size,
                )

            except TransferCancelled:
                emit(
                    current_file=rel,
                    current_bytes=file_transferred,
                    current_size=size,
                    status="cancelled",
                )
                raise

            except Exception as error:
                failed.append((str(path), repr(error)))
                processed_files += 1
                emit(
                    current_file=rel,
                    current_bytes=file_transferred,
                    current_size=size,
                )

        emit(status="complete")

        return {
            "uploaded": uploaded,
            "skipped": skipped,
            "failed": failed,
            "total_files": total_files,
            "total_bytes": total_bytes,
        }

    def verify_folder_by_size(
        self,
        local_folder: str | Path,
        remote_prefix: str = "",
    ):
        local_folder = Path(local_folder).resolve()
        remote_prefix = remote_prefix.strip("/")

        remote = {
            obj.key: obj.size
            for obj in self.iter_objects(
                remote_prefix + "/" if remote_prefix else ""
            )
        }

        missing: list[str] = []
        mismatched: list[tuple[str, int, int]] = []
        checked = 0

        for path in local_folder.rglob("*"):
            if not path.is_file():
                continue

            rel = path.relative_to(local_folder).as_posix()
            key = f"{remote_prefix}/{rel}" if remote_prefix else rel
            size = path.stat().st_size
            checked += 1

            if key not in remote:
                missing.append(key)
            elif remote[key] != size:
                mismatched.append((key, size, remote[key]))

        return {
            "checked": checked,
            "missing": missing,
            "mismatched": mismatched,
        }


def human_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{value} B"
