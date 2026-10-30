from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
import os
import time
import traceback
import uuid

from botocore.exceptions import ClientError

from b2_backend import B2Backend, TransferCancelled


ACTIVE = {"starting", "running", "deleting"}
TERMINAL = {"complete", "completed_with_errors", "error", "cancelled", "skipped"}


@dataclass
class Transfer:
    id: str
    owner: str
    kind: str
    label: str
    status: str = "starting"
    progress: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cancel: Event = field(default_factory=Event)
    updated_at: float = field(default_factory=time.monotonic)


class TransferManager:
    """Process-local transfer owner. Nothing survives a Streamlit restart."""

    def __init__(self, limit: int = 3, disconnect_timeout: float = 5.0):
        self.limit = limit
        self.disconnect_timeout = disconnect_timeout
        self._lock = Lock()
        self._items: dict[str, Transfer] = {}
        self._heartbeats: dict[str, float] = {}
        Thread(target=self._watch_sessions, daemon=True, name="transfer-watchdog").start()

    def heartbeat(self, owner: str) -> None:
        with self._lock:
            self._heartbeats[owner] = time.monotonic()

    def active_count(self) -> int:
        with self._lock:
            return sum(item.status in ACTIVE for item in self._items.values())

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            return [self._snapshot(item) for item in self._items.values() if item.owner == owner]

    def clear_terminal(self, owner: str) -> None:
        with self._lock:
            self._items = {
                key: item for key, item in self._items.items()
                if item.owner != owner or item.status in ACTIVE
            }

    def stop(self, owner: str, transfer_id: str) -> None:
        with self._lock:
            item = self._items.get(transfer_id)
            if item and item.owner == owner and item.status in ACTIVE:
                item.cancel.set()
                # Stop vanishes immediately, as requested.
                self._items.pop(transfer_id, None)

    def start(
        self,
        owner: str,
        kind: str,
        label: str,
        operation: Callable[[Transfer], None],
    ) -> str:
        with self._lock:
            if sum(item.status in ACTIVE for item in self._items.values()) >= self.limit:
                raise RuntimeError("Three transfers are already active.")
            transfer_id = uuid.uuid4().hex
            item = Transfer(transfer_id, owner, kind, label)
            self._items[transfer_id] = item

        def run() -> None:
            try:
                self.update(item, status="running")
                operation(item)
                if item.cancel.is_set():
                    raise TransferCancelled()
                if item.status in ACTIVE:
                    self.update(item, status="complete")
            except TransferCancelled:
                self.update(item, status="cancelled")
            except Exception:
                self.update(item, status="error", error=traceback.format_exc())

        Thread(target=run, daemon=True, name=f"transfer-{transfer_id[:8]}").start()
        return transfer_id

    def update(self, item: Transfer, *, status: str | None = None, error: str | None = None, **values: Any) -> None:
        with self._lock:
            if status is not None:
                item.status = status
            if error is not None:
                item.error = error
            item.progress.update(values)
            item.updated_at = time.monotonic()

    def _snapshot(self, item: Transfer) -> dict[str, Any]:
        return {
            "id": item.id,
            "kind": item.kind,
            "label": item.label,
            "status": item.status,
            "error": item.error,
            **item.progress,
        }

    def _watch_sessions(self) -> None:
        while True:
            time.sleep(1)
            now = time.monotonic()
            with self._lock:
                stale = {
                    owner for owner, heartbeat in self._heartbeats.items()
                    if now - heartbeat > self.disconnect_timeout
                }
                for item in self._items.values():
                    if item.owner in stale and item.status in ACTIVE:
                        item.cancel.set()
                for owner in stale:
                    self._heartbeats.pop(owner, None)
                self._items = {
                    key: item for key, item in self._items.items()
                    if item.owner not in stale
                }


def upload_file_operation(manager: TransferManager, local_path: str, remote_key: str):
    def operation(item: Transfer) -> None:
        backend = B2Backend()
        size = Path(local_path).stat().st_size
        try:
            if int(backend.head_object(remote_key)["ContentLength"]) == size:
                manager.update(item, status="skipped", total_bytes=size, transferred_bytes=size)
                return
        except ClientError as error:
            if error.response.get("Error", {}).get("Code", "") not in {"404", "NotFound", "NoSuchKey"}:
                raise

        manager.update(item, total_bytes=size, transferred_bytes=0, current_file=Path(local_path).name)
        backend.upload_file(
            local_path,
            remote_key,
            progress_callback=lambda done, total: manager.update(
                item, total_bytes=total, transferred_bytes=done
            ),
            cancel_token=item.cancel,
        )
    return operation


def upload_folder_operation(manager: TransferManager, local_path: str, remote_prefix: str):
    def operation(item: Transfer) -> None:
        backend = B2Backend()
        result = backend.upload_folder(
            local_path,
            remote_prefix,
            True,
            progress_callback=lambda info: manager.update(
                item,
                status=info.get("status", "running"),
                total_bytes=info.get("total_bytes", 0),
                transferred_bytes=info.get("processed_bytes", 0),
                total_files=info.get("total_files", 0),
                processed_files=info.get("processed_files", 0),
                current_file=info.get("current_file", ""),
                uploaded=info.get("uploaded", 0),
                skipped=info.get("skipped", 0),
                failed=info.get("failed", 0),
            ),
            cancel_token=item.cancel,
        )
        failures = result["failed"]
        manager.update(
            item,
            status="completed_with_errors" if failures else "complete",
            failed=len(failures),
            error="\n".join(f"{path}: {reason}" for path, reason in failures),
        )
    return operation


def download_operation(manager: TransferManager, remote_key: str, local_path: str):
    def operation(item: Transfer) -> None:
        backend = B2Backend()
        destination = Path(local_path)
        total = int(backend.head_object(remote_key)["ContentLength"])
        if destination.is_file() and destination.stat().st_size == total:
            manager.update(item, status="skipped", total_bytes=total, transferred_bytes=total)
            return
        temporary = destination.with_name(f".{destination.name}.{item.id}.part")
        manager.update(item, total_bytes=total, transferred_bytes=0, current_file=destination.name)
        try:
            backend.download_file(
                remote_key,
                temporary,
                progress_callback=lambda done, size: manager.update(
                    item, total_bytes=size, transferred_bytes=done
                ),
                cancel_token=item.cancel,
            )
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    return operation


def copy_move_operation(
    manager: TransferManager,
    source_key: str,
    destination_key: str,
    source_is_folder: bool,
    move: bool,
    overwrite: bool,
):
    def operation(item: Transfer) -> None:
        backend = B2Backend()
        if source_is_folder:
            result = backend.copy_folder(
                source_key, destination_key, move=move, overwrite=overwrite,
                progress_callback=lambda info: manager.update(
                    item,
                    status=info.get("status", "running"),
                    total_bytes=info.get("total_bytes", 0),
                    transferred_bytes=info.get("processed_bytes", 0),
                    total_files=info.get("total_files", 0),
                    processed_files=info.get("processed_files", 0),
                    current_file=info.get("current_file", ""),
                    copied=info.get("copied", 0),
                    deleted=info.get("deleted", 0),
                    failed=info.get("failed", 0),
                ),
                cancel_token=item.cancel,
            )
            failures = result["failed"]
            manager.update(
                item,
                status="completed_with_errors" if failures else "complete",
                error="\n".join(f"{key}: {reason}" for key, reason in failures),
            )
            return

        total = backend.copy_object(
            source_key, destination_key, overwrite=overwrite,
            progress_callback=lambda done, size: manager.update(
                item, total_bytes=size, transferred_bytes=done
            ),
            cancel_token=item.cancel,
        )
        if move:
            manager.update(item, status="deleting")
            if item.cancel.is_set():
                raise TransferCancelled()
            backend.delete_file(source_key)
        manager.update(item, total_bytes=total, transferred_bytes=total)
    return operation
