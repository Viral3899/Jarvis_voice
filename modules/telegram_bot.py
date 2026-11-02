"""
Telegram module — read & reply messages via Bot API.
Uses python-telegram-bot library.

Setup:
1. Message @BotFather on Telegram → /newbot
2. Copy the token to .env TELEGRAM_BOT_TOKEN
3. Message your bot, then get chat ID from https://api.telegram.org/bot<TOKEN>/getUpdates
4. Set TELEGRAM_CHAT_ID in .env
"""

import os
import asyncio
import threading
from telegram import Bot
from telegram.error import TelegramError


_TELEGRAM_UPDATES_LOCK = threading.Lock()


class TelegramModule:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.last_update_id = 0

        if not self.token or "your_" in self.token:
            print("⚠ Telegram: Set TELEGRAM_BOT_TOKEN in .env")

    async def _get_updates(self) -> list[dict]:
        token = self.token
        if not token or "your_" in token:
            return []

        try:
            async with Bot(token=token) as bot:
                updates = await bot.get_updates(
                    offset=self.last_update_id + 1, timeout=5
                )
                messages = []
                for update in updates:
                    self.last_update_id = update.update_id
                    if update.message:
                        messages.append({
                            "id": update.update_id,
                            "from": update.message.from_user.first_name,
                            "chat_id": update.message.chat_id,
                            "text": update.message.text or "",
                            "date": str(update.message.date),
                        })
                return messages
        except TelegramError as e:
            error = str(e)
            if "conflict" in error.lower() and "getupdates" in error.lower():
                print(
                    "⚠ Telegram polling conflict: another Jarvis process or "
                    "client is polling this bot token. Stop the other poller."
                )
            else:
                print(f"⚠ Telegram error: {e}")
            return []

    def get_new_messages(self) -> list[dict]:
        with _TELEGRAM_UPDATES_LOCK:
            return asyncio.run(self._get_updates())

    async def _send(self, chat_id: str, text: str):
        token = self.token
        if token and "your_" not in token:
            async with Bot(token=token) as bot:
                await bot.send_message(chat_id=chat_id, text=text)

    def send_message(self, text: str, chat_id: str = None) -> bool:
        if not self.token or "your_" in self.token:
            return False
        target = chat_id or self.chat_id
        if not target:
            return False
        try:
            asyncio.run(self._send(target, text))
            return True
        except Exception as e:
            print(f"⚠ Telegram send error: {e}")
            return False

    def reply_to(self, message: dict, reply_text: str) -> bool:
        return self.send_message(reply_text, chat_id=str(message["chat_id"]))

    def get_summary(self) -> str:
        msgs = self.get_new_messages()
        if not msgs:
            return "✈️ No new Telegram messages."
        lines = [f"✈️ {len(msgs)} new Telegram messages:"]
        for m in msgs:
            lines.append(f"  • {m['from']}: {m['text'][:60]}")
        return "\n".join(lines)
