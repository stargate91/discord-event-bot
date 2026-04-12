"""Parse duration strings like 15m, 2h, 1d into timedelta."""

import datetime
import re


def parse_offset(offset_str):
    match = re.match(r"^(\d+)([mhd])$", str(offset_str).strip().lower())
    if not match:
        return datetime.timedelta(hours=1)
    val, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        return datetime.timedelta(minutes=val)
    if unit == "h":
        return datetime.timedelta(hours=val)
    if unit == "d":
        return datetime.timedelta(days=val)
    return datetime.timedelta(hours=1)
