"""
Windows notification system — toast notifications + sound alerts.
"""

import threading
from plyer import notification


def notify(title: str, message: str, timeout: int = 10):
    """Show a Windows toast notification (non-blocking)."""
    def _send():
        try:
            notification.notify(
                title=f"🤖 Jarvis: {title}",
                message=message,
                timeout=timeout,
                app_name="Jarvis Agent",
            )
        except Exception as e:
            print(f"⚠ Notification error: {e}")

    threading.Thread(target=_send, daemon=True).start()
