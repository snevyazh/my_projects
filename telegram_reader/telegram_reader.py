"""Read Telegram cloud chats using the signed-in user's account."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import Channel, Chat, User
from tqdm import tqdm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read chats and messages accessible to your Telegram account."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dialogs = sub.add_parser("dialogs", help="List chats, groups, and channels")
    dialogs.add_argument("--limit", type=positive_int, default=100)
    dialogs.add_argument("--all", action="store_true", help="Include archived dialogs")

    messages = sub.add_parser("messages", help="Read message history from one chat")
    messages.add_argument("chat", help="Chat ID, @username, username, or exact title")
    messages.add_argument("--limit", type=positive_int, default=50)
    messages.add_argument("--search", help="Only return messages matching this text")
    messages.add_argument("--offset-date", type=iso_datetime, help="Messages before this ISO date")
    messages.add_argument("--json", action="store_true", help="Print JSON Lines")

    search = sub.add_parser("search", help="Search messages across your dialogs")
    search.add_argument("query")
    search.add_argument("--limit", type=positive_int, default=100)
    search.add_argument("--json", action="store_true", help="Print JSON Lines")

    export = sub.add_parser("export", help="Export one chat's messages to a JSON file")
    export.add_argument("chat", help="Chat ID, @username, username, or exact title")
    export.add_argument("--limit", type=positive_int, default=1000)
    export.add_argument("--output", type=Path, help="Output path (default: exports/<chat>.json)")

    download = sub.add_parser("download", help="Download text metadata and all attached media")
    download.add_argument("chat", help="Chat ID, @username, username, or exact title")
    download.add_argument(
        "--limit", type=positive_int, default=None,
        help="Maximum newest messages to download (default: complete available history)",
    )
    download.add_argument(
        "--output", type=Path,
        help="Output directory (default: downloads/<chat-id>)",
    )
    download.add_argument(
        "--max-media-mb",
        type=nonnegative_float,
        default=10.0,
        help="Skip media larger than this many MB (default: 10; 0 disables the limit)",
    )
    return parser


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def iso_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use ISO 8601, e.g. 2026-10-30 or 2026-10-30T12:00:00Z") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def credentials() -> tuple[int, str, str]:
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_SESSION", "sessions/telegram_reader").strip()
    if not api_id or not api_hash:
        raise RuntimeError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH. Copy .env.example to .env and fill them in.")
    try:
        numeric_id = int(api_id)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID must be a number.") from exc
    Path(session).parent.mkdir(parents=True, exist_ok=True)
    return numeric_id, api_hash, session


def entity_name(entity: Any) -> str:
    if isinstance(entity, User):
        return " ".join(part for part in (entity.first_name, entity.last_name) if part) or entity.username or str(entity.id)
    return getattr(entity, "title", None) or getattr(entity, "username", None) or str(getattr(entity, "id", "unknown"))


def entity_kind(entity: Any) -> str:
    if isinstance(entity, User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return type(entity).__name__.lower()


def safe_folder_name(name: str, fallback: str = "chat") -> str:
    """Return a Windows-safe folder name while keeping it recognizable."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if cleaned.upper() in reserved:
        cleaned = f"_{cleaned}"
    return cleaned[:120].rstrip(" .") or fallback


def media_destination(message: Any, output: Path) -> Path:
    """Build a stable, human-friendly path for a message attachment."""
    if message.photo:
        category = "photos"
    elif message.video:
        category = "videos"
    elif message.gif:
        category = "gifs"
    elif message.voice or message.audio:
        category = "audio"
    elif message.sticker:
        category = "stickers"
    elif message.document:
        category = "documents"
    else:
        category = "other"

    telegram_name = getattr(message.file, "name", None)
    extension = getattr(message.file, "ext", None) or ""
    if telegram_name:
        original = Path(telegram_name)
        stem = safe_folder_name(original.stem, fallback="file")
        suffix = original.suffix or extension
        filename = f"{message.id}_{stem}{suffix}"
    else:
        filename = f"{message.id}{extension}"
    return output / category / filename


def is_mp3(message: Any) -> bool:
    """Return whether a message attachment is an MP3 audio file."""
    file = getattr(message, "file", None)
    name = getattr(file, "name", None) or ""
    extension = getattr(file, "ext", None) or ""
    mime_type = getattr(file, "mime_type", None) or ""
    return (
        Path(name).suffix.casefold() == ".mp3"
        or extension.casefold() == ".mp3"
        or mime_type.casefold() in {"audio/mpeg", "audio/mp3"}
    )


async def resolve_chat(client: TelegramClient, reference: str) -> Any:
    candidate: int | str = int(reference) if reference.lstrip("-").isdigit() else reference
    try:
        return await client.get_entity(candidate)
    except (ValueError, RPCError):
        wanted = reference.casefold().lstrip("@")
        async for dialog in client.iter_dialogs(limit=None):
            username = (getattr(dialog.entity, "username", None) or "").casefold()
            if dialog.name.casefold() == wanted or username == wanted:
                return dialog.entity
    raise ValueError(f"Chat not found: {reference!r}. Run 'dialogs' to see valid IDs and names.")


async def message_record(message: Any, chat: Any | None = None) -> dict[str, Any]:
    sender = await message.get_sender()
    current_chat = chat or await message.get_chat()
    return {
        "chat_id": getattr(current_chat, "id", None),
        "chat": entity_name(current_chat),
        "message_id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "sender_id": getattr(sender, "id", None),
        "sender": entity_name(sender) if sender else None,
        "text": message.raw_text or "",
        "has_media": message.media is not None,
        "reply_to_message_id": message.reply_to_msg_id,
    }


def print_record(record: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(record, ensure_ascii=False))
        return
    date = record["date"] or "unknown date"
    sender = record["sender"] or "unknown sender"
    chat = f' [{record["chat"]}]' if record.get("chat") else ""
    text = record["text"] or ("<media>" if record["has_media"] else "<empty>")
    print(f'{date}{chat} {sender} #{record["message_id"]}: {text}')


async def run(args: argparse.Namespace) -> None:
    api_id, api_hash, session = credentials()
    client = TelegramClient(session, api_id, api_hash)
    async with client:
        if args.command == "dialogs":
            async for dialog in client.iter_dialogs(limit=args.limit, archived=None if args.all else False):
                username = getattr(dialog.entity, "username", None)
                suffix = f" @{username}" if username else ""
                print(f"{dialog.id}\t{entity_kind(dialog.entity):10}\t{dialog.name}{suffix}")
            return

        if args.command == "search":
            async for message in client.iter_messages(None, search=args.query, limit=args.limit):
                print_record(await message_record(message), args.json)
            return

        chat = await resolve_chat(client, args.chat)
        if args.command == "messages":
            async for message in client.iter_messages(
                chat, limit=args.limit, search=args.search, offset_date=args.offset_date
            ):
                print_record(await message_record(message, chat), args.json)
            return

        if args.command == "download":
            folder_name = safe_folder_name(
                entity_name(chat), fallback=str(getattr(chat, "id", "chat"))
            )
            output = args.output or Path("downloads") / folder_name
            output.mkdir(parents=True, exist_ok=True)
            count_result = await client.get_messages(chat, limit=0)
            available = count_result.total
            planned = min(available, args.limit) if args.limit is not None else available
            print(f"Channel has {available:,} messages; processing {planned:,}.")
            records = []
            downloaded = 0
            reused = 0
            skipped = 0
            max_media_bytes = int(args.max_media_mb * 1024 * 1024)
            progress = tqdm(total=planned, desc="Messages", unit="msg", dynamic_ncols=True)
            try:
                async for message in client.iter_messages(chat, limit=args.limit):
                    record = await message_record(message, chat)
                    record["media_path"] = None
                    record["media_error"] = None
                    media_size = getattr(message.file, "size", None)
                    record["media_size_bytes"] = media_size
                    if message.media is not None:
                        if is_mp3(message):
                            skipped += 1
                            record["media_error"] = "Skipped: MP3 media is filtered out"
                        elif max_media_bytes and media_size and media_size > max_media_bytes:
                            skipped += 1
                            record["media_error"] = (
                                f"Skipped: media is {media_size / 1024 / 1024:.1f} MB; "
                                f"limit is {args.max_media_mb:g} MB"
                            )
                        else:
                            destination = media_destination(message, output)
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            if destination.is_file():
                                saved_path = str(destination)
                                reused += 1
                            else:
                                try:
                                    saved_path = await message.download_media(file=str(destination))
                                except TimeoutError as exc:
                                    destination.unlink(missing_ok=True)
                                    saved_path = None
                                    skipped += 1
                                    record["media_error"] = f"{type(exc).__name__}: {exc}"
                                    tqdm.write(f"Skipped timed-out media for message {message.id}")
                                else:
                                    if saved_path:
                                        downloaded += 1
                            if saved_path:
                                saved = Path(saved_path)
                                try:
                                    record["media_path"] = saved.relative_to(output).as_posix()
                                except ValueError:
                                    record["media_path"] = str(saved)
                    records.append(record)
                    progress.update(1)
                    progress.set_postfix(
                        downloaded=downloaded,
                        reused=reused,
                        skipped=skipped,
                        refresh=False,
                    )
            finally:
                progress.close()
            records.reverse()
            index = output / "messages.json"
            index.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                f"Saved {len(records)} messages under {output} "
                f"({downloaded} media downloaded, {reused} already present, "
                f"{skipped} skipped)."
            )
            return

        records = []
        async for message in client.iter_messages(chat, limit=args.limit, reverse=True):
            records.append(await message_record(message, chat))
        output = args.output or Path("exports") / f"{getattr(chat, 'id', 'chat')}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Exported {len(records)} messages to {output}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, RPCError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
