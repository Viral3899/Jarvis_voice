import threading


CHROME_START_LOCK = threading.Lock()


def browser_error_summary(error: Exception) -> str:
    """Return one concise, actionable line instead of Selenium's full traceback."""
    message_lines = []
    for line in str(error).splitlines():
        line = line.strip()
        if line.lower().startswith("stacktrace"):
            break
        if line.lower().startswith("message:"):
            line = line.partition(":")[2].strip()
        if line:
            message_lines.append(line)
    message = " ".join(message_lines)
    if not message:
        message = (
            "Chrome did not become ready. Close conflicting Chrome windows, "
            "check the browser profile, and complete login/QR setup."
        )
    elif (
        "cannot connect to chrome" in message.lower()
        or "chrome not reachable" in message.lower()
    ):
        message = (
            "Chrome started but its debugging endpoint was unreachable. "
            "Close stale Chrome windows using the Jarvis profile and restart Jarvis."
        )
    return f"{type(error).__name__}: {message[:240]}"
