# watch-and-send

A Telegram watcher that listens to one or more chats or bots and
automatically forwards the content you care about to your Saved Messages.

## What it does

- Watches any chats/bots you name (`@username`, chat id, or `-100...` id)
- Forwards matching messages to your Saved Messages
- Skips messages that have "no-forward" protection enabled
- Handles Telegram flood-wait limits automatically and retries
- Prints a heartbeat line so you can see it's still alive
- Asks what to watch every run — no config to edit for the targets

By default it saves **videos only**. To also keep photos, audio,
documents or plain text, add them to `WANTED_TYPES` in the script
(see also `MIN_SIZE_MB` to skip small files).

## Setup

1. Get an **API id** and **API hash** from https://my.telegram.org
   (API development tools → create an app).

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Then open `config.py` and fill in your `API_ID`, `API_HASH`, and a
   `SESSION_NAME` (any name — it becomes your local session file).

   This file should only live in your machine, do not post it anywhere.

4. Run it:

   ```bash
   python watch_and_save.py
   ```

   On the first run Telegram will ask for your phone number and login
   code. After that, type one or more `@usernames` or ids of the chats
   to watch (space or comma separated). Press `Ctrl+C` to stop.

## Notes

- Your login session is stored in a local `*.session` file. Keep it
  private — it's already covered by `.gitignore` so it never gets pushed.
- Getting flood-waited? Increase `FLOOD_WAIT_SLEEP` in the script.
