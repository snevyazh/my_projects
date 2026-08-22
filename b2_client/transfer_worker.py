from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
import traceback

from b2_backend import (
    B2Backend,
    TransferCancelled,
)


class FileCancelToken:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def is_set(self) -> bool:
        return self.path.exists()


def atomic_write_json(
    path: Path,
    data: dict,
):
    path.parent.mkdir(parents=True, exist_ok=True)

    data["heartbeat"] = time.time()
    data["pid"] = os.getpid()

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path,
    )


def base_status() -> dict:
    return {
        "status": "starting",
        "started_at": time.time(),
        "heartbeat": time.time(),
        "pid": os.getpid(),
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
    }


def run_single_upload(args):
    backend = B2Backend()
    status_path = Path(args.status_file)
    cancel = FileCancelToken(args.stop_file)

    local_path = Path(args.local_path)
    total = local_path.stat().st_size

    status = base_status()
    status.update(
        {
            "status": "running",
            "total_bytes": total,
            "current_file": local_path.name,
        }
    )
    atomic_write_json(status_path, status)

    def on_progress(
        transferred: int,
        total_bytes: int,
    ):
        status.update(
            {
                "status": "running",
                "total_bytes": total_bytes,
                "transferred_bytes": transferred,
                "current_bytes": transferred,
                "current_size": total_bytes,
            }
        )
        atomic_write_json(
            status_path,
            status,
        )

    try:
        backend.upload_file(
            local_path,
            args.remote_key,
            progress_callback=on_progress,
            cancel_token=cancel,
        )

        status.update(
            {
                "status": "complete",
                "transferred_bytes": total,
                "current_bytes": total,
            }
        )

    except TransferCancelled:
        status["status"] = "cancelled"

    except Exception:
        status["status"] = "error"
        status["error"] = traceback.format_exc()

    atomic_write_json(
        status_path,
        status,
    )


def run_folder_upload(args):
    backend = B2Backend()
    status_path = Path(args.status_file)
    cancel = FileCancelToken(args.stop_file)

    status = base_status()
    status["status"] = "running"
    atomic_write_json(
        status_path,
        status,
    )

    def on_progress(info: dict):
        status.update(
            {
                "status": info.get("status", "running"),
                "total_bytes": info.get("total_bytes", 0),
                "transferred_bytes": info.get("processed_bytes", 0),
                "total_files": info.get("total_files", 0),
                "processed_files": info.get("processed_files", 0),
                "current_file": info.get("current_file", ""),
                "current_bytes": info.get("current_bytes", 0),
                "current_size": info.get("current_size", 0),
                "uploaded": info.get("uploaded", 0),
                "skipped": info.get("skipped", 0),
                "failed": info.get("failed", 0),
            }
        )
        atomic_write_json(
            status_path,
            status,
        )

    try:
        result = backend.upload_folder(
            args.local_path,
            args.remote_prefix,
            args.skip_same,
            progress_callback=on_progress,
            cancel_token=cancel,
        )

        status.update(
            {
                "status": "complete",
                "total_bytes": result["total_bytes"],
                "transferred_bytes": result["total_bytes"],
                "total_files": result["total_files"],
                "processed_files": result["total_files"],
                "uploaded": result["uploaded"],
                "skipped": result["skipped"],
                "failed": len(result["failed"]),
            }
        )

    except TransferCancelled:
        status["status"] = "cancelled"

    except Exception:
        status["status"] = "error"
        status["error"] = traceback.format_exc()

    atomic_write_json(
        status_path,
        status,
    )


def run_download(args):
    backend = B2Backend()
    status_path = Path(args.status_file)
    cancel = FileCancelToken(args.stop_file)

    status = base_status()
    status.update(
        {
            "status": "running",
            "current_file": Path(args.remote_key).name,
        }
    )
    atomic_write_json(
        status_path,
        status,
    )

    def on_progress(
        transferred: int,
        total_bytes: int,
    ):
        status.update(
            {
                "status": "running",
                "total_bytes": total_bytes,
                "transferred_bytes": transferred,
                "current_bytes": transferred,
                "current_size": total_bytes,
            }
        )
        atomic_write_json(
            status_path,
            status,
        )

    try:
        backend.download_file(
            args.remote_key,
            args.local_path,
            progress_callback=on_progress,
            cancel_token=cancel,
        )

        status["status"] = "complete"

    except TransferCancelled:
        status["status"] = "cancelled"

    except Exception:
        status["status"] = "error"
        status["error"] = traceback.format_exc()

    atomic_write_json(
        status_path,
        status,
    )


def run_copy_move(args):
    status_path = Path(args.status_file)
    cancel = FileCancelToken(args.stop_file)
    status = base_status()
    status.update(
        {
            "status": "starting",
            "action": "move" if args.move else "copy",
            "source_is_folder": args.source_is_folder,
        }
    )
    atomic_write_json(status_path, status)

    try:
        backend = B2Backend()

        if args.source_is_folder:
            def on_progress(info: dict):
                status.update(
                    {
                        "status": info.get("status", "running"),
                        "total_bytes": info.get("total_bytes", 0),
                        "transferred_bytes": info.get("processed_bytes", 0),
                        "total_files": info.get("total_files", 0),
                        "processed_files": info.get("processed_files", 0),
                        "current_file": info.get("current_file", ""),
                        "current_bytes": info.get("current_bytes", 0),
                        "current_size": info.get("current_size", 0),
                        "copied": info.get("copied", 0),
                        "deleted": info.get("deleted", 0),
                        "failed": info.get("failed", 0),
                    }
                )
                atomic_write_json(status_path, status)

            result = backend.copy_folder(
                args.source_key,
                args.destination_key,
                move=args.move,
                overwrite=args.overwrite,
                progress_callback=on_progress,
                cancel_token=cancel,
            )
            failed = len(result["failed"])
            status.update(
                {
                    "status": (
                        "complete" if failed == 0 else "completed_with_errors"
                    ),
                    "total_bytes": result["total_bytes"],
                    "transferred_bytes": result["processed_bytes"],
                    "total_files": result["total_files"],
                    "processed_files": result["total_files"],
                    "copied": result["copied"],
                    "deleted": result["deleted"],
                    "failed": failed,
                    "error": "\n".join(
                        f"{key}: {error}" for key, error in result["failed"]
                    ),
                }
            )

        else:
            source_key = args.source_key.strip("/")
            destination_key = args.destination_key.strip("/")

            if source_key == destination_key:
                raise ValueError("Source and destination object keys must differ.")

            meta = backend.head_object(source_key)
            total = int(meta["ContentLength"])
            status.update(
                {
                    "status": "running",
                    "total_bytes": total,
                    "total_files": 1,
                    "current_file": source_key,
                    "current_size": total,
                }
            )
            atomic_write_json(status_path, status)

            def on_progress(transferred: int, total_bytes: int):
                status.update(
                    {
                        "status": "running",
                        "total_bytes": total_bytes,
                        "transferred_bytes": transferred,
                        "current_bytes": transferred,
                        "current_size": total_bytes,
                    }
                )
                atomic_write_json(status_path, status)

            backend.copy_object(
                source_key,
                destination_key,
                overwrite=args.overwrite,
                progress_callback=on_progress,
                cancel_token=cancel,
            )
            status.update(
                {
                    "copied": 1,
                    "processed_files": 1,
                    "transferred_bytes": total,
                    "current_bytes": total,
                }
            )

            if args.move:
                if cancel.is_set():
                    raise TransferCancelled("Move cancelled before source deletion.")

                status["status"] = "deleting"
                atomic_write_json(status_path, status)
                backend.delete_file(source_key)
                status["deleted"] = 1

            status["status"] = "complete"

    except TransferCancelled:
        status["status"] = "cancelled"

    except Exception:
        status["status"] = "error"
        status["error"] = traceback.format_exc()

    atomic_write_json(status_path, status)

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "mode",
        choices=[
            "upload_file",
            "upload_folder",
            "download",
            "copy_move",
        ],
    )

    parser.add_argument(
        "--status-file",
        required=True,
    )

    parser.add_argument(
        "--stop-file",
        required=True,
    )

    parser.add_argument(
        "--local-path",
        required=True,
    )

    parser.add_argument(
        "--remote-key",
        default="",
    )

    parser.add_argument(
        "--remote-prefix",
        default="",
    )

    parser.add_argument(
        "--skip-same",
        action="store_true",
    )

    parser.add_argument(
        "--source-key",
        default="",
    )

    parser.add_argument(
        "--destination-key",
        default="",
    )

    parser.add_argument(
        "--source-is-folder",
        action="store_true",
    )

    parser.add_argument(
        "--move",
        action="store_true",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        if args.mode == "upload_file":
            run_single_upload(args)

        elif args.mode == "upload_folder":
            run_folder_upload(args)

        elif args.mode == "download":
            run_download(args)

        elif args.mode == "copy_move":
            run_copy_move(args)

    finally:
        stop_file = Path(args.stop_file)

        if stop_file.exists():
            try:
                stop_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
