"""
Windows notification system — toast notifications + sound alerts.
"""

import threading
from plyer import notification


def _fit_windows_notification_text(text: str, max_units: int) -> str:
    """Keep text within a Windows WCHAR buffer, including the null terminator."""
    limit = max_units - 1
    result = []
    used_units = 0
    for character in text:
        units = len(character.encode("utf-16-le")) // 2
        if used_units + units > limit:
            if limit:
                while result and used_units + 1 > limit:
                    removed = result.pop()
                    used_units -= len(removed.encode("utf-16-le")) // 2
                result.append("…")
            break
        result.append(character)
        used_units += units
    return "".join(result)


def notify(title: str, message: str, timeout: int = 10):
    """Show a Windows toast notification (non-blocking)."""
    def _send():
        try:
            notification.notify(
                title=_fit_windows_notification_text(f"🤖 Jarvis: {title}", 64),
                message=_fit_windows_notification_text(message, 256),
                timeout=timeout,
                app_name=_fit_windows_notification_text("Jarvis Agent", 128),
            )
        except Exception as e:
            print(f"⚠ Notification error: {e}")

    threading.Thread(target=_send, daemon=True).start()
