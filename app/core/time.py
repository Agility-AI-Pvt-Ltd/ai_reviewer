import datetime as dt

def get_ist_now() -> dt.datetime:
    """Return the current time in IST (naive) for database storage."""
    return dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
