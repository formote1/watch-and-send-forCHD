from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
from telethon.errors import FloodWaitError
from datetime import datetime
import asyncio
import re

# Your credentials live in config.py — create it from config.example.py
# (cp config.example.py config.py) and fill in your own values.
from config import API_ID, API_HASH, SESSION_NAME

# The chats to watch are asked for when the script starts — nothing to edit
# here. Just run it and type one or more @usernames (bot or person), separated
# by spaces or commas.

# Message types that trigger a save. Only "video" is active; to also save
# photos, audio, documents or plain text, add their names here — the
# detection in detect_type() already knows how to spot them.
WANTED_TYPES = {"video"}

# Optional: skip videos smaller than this (in MB). 0 = keep everything.
MIN_SIZE_MB = 0

# Extra wait applied if Telegram asks us to slow down (flood-wait errors).
FLOOD_WAIT_SLEEP = 60

# How often to print a "still listening" line, in seconds — proof it's alive
# and not stuck.
HEARTBEAT_SECONDS = 300

BANNER = r"""
 _       __     __    ___    _   _    __  __    ____     _     __  __  _____
| |     / /    / _|  / _ \  | | | |  |  \/  |  / ___|   / \   |  \/  || ____|
| | /| / /    | |_  | | | | | | | |  | |\/| | | |  _   / _ \  | |\/| ||  _|
| |/ V/ /     |  _| | |_| | | |_| |  | |  | | | |_| | / ___ \ | |  | || |___
|__/|_/       |_|    \___/   \___/   |_|  |_|  \____|/_/   \_\|_|  |_||_____|

        saved-messages watcher online...
"""


def ts():
    return datetime.now().strftime("%H:%M:%S")


def detect_type(msg):
    """Classify a message into a known type (or None)."""
    if bool(msg.video) or (msg.file and msg.file.mime_type and "video" in msg.file.mime_type):
        return "video"
    if bool(msg.photo):
        return "photo"
    if bool(msg.audio) or bool(msg.voice):
        return "audio"
    if bool(msg.document):
        return "document"
    if msg.text:
        return "text"
    return None


def coerce_target(value):
    """Turn user input into something Telethon can resolve: a -100xxxxxxxxxx
    id becomes a PeerChannel, a bare number stays a number (user/chat id),
    anything else is treated as a @username."""
    value = value.strip()
    if value.lstrip("-").isdigit():
        number = int(value)
        if str(number).startswith("-100"):
            return PeerChannel(int(str(number)[4:]))
        return number
    return value


async def resolve_entity(client, value, timeout=60):
    """Resolve a username/id to an entity, with a timeout so a bad target
    can never make the script hang forever."""
    return await asyncio.wait_for(
        client.get_input_entity(coerce_target(value)), timeout=timeout
    )


def parse_targets(raw):
    """Split user input into a clean, de-duplicated list of targets —
    commas and/or spaces both work: '@a @b' or '@a, @b'."""
    targets = []
    for part in re.split(r"[,\s]+", raw.strip()):
        part = part.strip()
        if part and part not in targets:
            targets.append(part)
    return targets


def describe(event, msg):
    """Human-readable 'chat / sender' label for log lines."""
    chat = event.chat
    chat_name = (
        getattr(chat, "title", None)
        or getattr(chat, "username", None)
        or getattr(chat, "first_name", None)
        or "chat"
    )
    sender = (
        getattr(msg.sender, "username", None)
        or getattr(msg.sender, "first_name", None)
        or getattr(msg.sender, "title", None)
        or f"id {msg.sender_id}"
    )
    return f"{chat_name} / {sender}"


async def main():
    print(BANNER, flush=True)

    # Ask what to watch up front, so the script is never silently idle.
    target_raw = (input("Chats to listen to (space/comma-separated @usernames or ids): ") or "").strip()
    while not target_raw:
        target_raw = (input("Please type one or more @usernames or ids: ") or "").strip()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    print(f"Connecting with session '{SESSION_NAME}'...", flush=True)
    await client.connect()
    if not await client.is_user_authorized():
        print("This session isn't logged in yet — Telegram will ask for your "
              "phone number and login code now.", flush=True)
        await client.start()

    me = await client.get_me()
    who = getattr(me, "username", None) or getattr(me, "first_name", None) or me.id
    print(f"Connected as {who} (id {me.id}).", flush=True)

    # Resolve every target once, with a timeout so a wrong username errors out
    # instead of hanging forever. Ones that fail are reported and skipped; if
    # none resolve, ask again.
    while True:
        resolved, failed = [], []
        for name in parse_targets(target_raw):
            try:
                resolved.append((name, await resolve_entity(client, name)))
            except Exception as e:
                failed.append((name, e))

        for name, e in failed:
            print(f"  couldn't resolve '{name}': {e}")

        if resolved:
            break

        print("None of those could be resolved.")
        target_raw = (input("Try again (@usernames or ids, blank = quit): ") or "").strip()
        if not target_raw:
            print("Nothing to watch — exiting.")
            await client.disconnect()
            return

    watch_entities = [entity for _, entity in resolved]
    watch_names = ", ".join(name for name, _ in resolved)

    print(f"Watching {len(watch_entities)} chat(s): {watch_names}")
    print(f"Saving {', '.join(sorted(WANTED_TYPES)) or 'nothing'} to your Saved Messages. Press Ctrl+C to stop.\n", flush=True)
    print(f"[{ts()}] listening...", flush=True)

    async def heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            print(f"[{ts()}] still listening on {watch_names} ...", flush=True)

    hb = asyncio.ensure_future(heartbeat())

    @client.on(events.NewMessage(chats=watch_entities))
    async def handler(event):
        msg = event.message

        t = detect_type(msg)
        if t not in WANTED_TYPES:
            return

        size_mb = (msg.file.size if msg.file else 0) / (1024 * 1024)
        if size_mb < MIN_SIZE_MB:
            return

        if msg.noforwards:
            print(f"[{ts()}] skipped  : {describe(event, msg)} #{msg.id} — noforward enabled", flush=True)
            return

        # Forward to "me" = your Saved Messages. Retry if Telegram asks
        # us to slow down; other errors are logged so the watcher stays up.
        try:
            while True:
                try:
                    await msg.forward_to("me")
                    break
                except FloodWaitError as e:
                    print(f"[{ts()}] flood wait: {e.seconds}s — sleeping...", flush=True)
                    await asyncio.sleep(max(e.seconds, FLOOD_WAIT_SLEEP))
            print(f"[{ts()}] saved    : {describe(event, msg)} #{msg.id} ({t}, {size_mb:.1f}MB)", flush=True)
        except Exception as e:
            print(f"[{ts()}] error    : {describe(event, msg)} #{msg.id} — {e}", flush=True)

    try:
        await client.run_until_disconnected()
    finally:
        hb.cancel()


asyncio.run(main())
