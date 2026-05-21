"""
utils/time_utils.py
-------------------
Timezone-aware helpers for Unix timestamps.
"""

import datetime
import pytz


def utc_to_local(unix_ts: int, tz_name: str = "Asia/Kolkata") -> str:
    """Convert a Unix timestamp to a human-readable local-time string."""
    tz = pytz.timezone(tz_name)
    utc_dt = datetime.datetime.utcfromtimestamp(unix_ts).replace(tzinfo=pytz.utc)
    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def now_utc() -> str:
    """Current UTC time as a formatted string."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def duration_str(seconds: int) -> str:
    """Format seconds as HH:MM:SS."""
    h, rem = divmod(abs(seconds), 3600)
    m, s = divmod(rem, 60)
    prefix = "-" if seconds < 0 else ""
    if h:
        return f"{prefix}{h}h {m:02d}m {s:02d}s"
    return f"{prefix}{m}m {s:02d}s"
