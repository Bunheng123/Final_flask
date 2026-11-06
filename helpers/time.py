from datetime import datetime, timezone, timedelta
from config import STORE_TIMEZONE

def utc_now() -> datetime:
    """
    Return timezone-naive current UTC datetime.
    All models must store timestamps created via this function.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

def to_local(dt: datetime, tz_name: str = None) -> datetime:
    """
    Convert a datetime to the display/reporting timezone (default: Asia/Phnom_Penh, GMT+7).
    If dt is timezone-naive, it is assumed to be UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    target_tz = tz_name or STORE_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo(target_tz))
    except Exception:
        # Robust fallback when tzdata is not available on Windows
        return dt.astimezone(timezone(timedelta(hours=7)))
