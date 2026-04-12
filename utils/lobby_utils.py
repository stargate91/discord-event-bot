"""Lobby (fill-to-start) single events: capacity and RSVP counting."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Union


def positive_status_ids(active_set: dict) -> List[str]:
    if active_set.get("positive"):
        return list(active_set["positive"])
    cnt = active_set.get("positive_count")
    if cnt is not None:
        return [o["id"] for o in active_set.get("options", [])[: int(cnt)]]
    return []


def effective_lobby_capacity(
    max_accepted: int,
    active_set: dict,
    role_limits: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    role_limits = role_limits or {}
    ma = int(max_accepted or 0)
    if ma > 0:
        return ma

    pos = positive_status_ids(active_set)
    if not pos:
        return None

    total = 0
    for opt in active_set.get("options", []):
        rid = opt.get("id")
        if rid not in pos:
            continue
        lim = role_limits.get(rid, opt.get("max_slots", 0))
        try:
            lim_i = int(lim) if lim is not None else 0
        except (TypeError, ValueError):
            lim_i = 0
        if lim_i <= 0:
            return None
        total += lim_i
    return total if total > 0 else None


def role_limits_from_extra(extra_data: Union[str, dict, None]) -> Dict[str, Any]:
    if not extra_data:
        return {}
    try:
        d = json.loads(extra_data) if isinstance(extra_data, str) else extra_data
        if isinstance(d, dict):
            return d.get("role_limits") or {}
    except Exception:
        pass
    return {}


def count_positive_rsvps(rsvps_rows: Sequence[Any], positive_statuses: Sequence[str]) -> int:
    pos_set = set(positive_statuses)
    n = 0
    for row in rsvps_rows:
        st = row["status"]
        if st in pos_set and not str(st).startswith("wait_"):
            n += 1
    return n


def lobby_is_full(count: int, cap: int) -> bool:
    return cap > 0 and count >= cap
