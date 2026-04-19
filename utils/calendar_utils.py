import urllib.parse
import datetime
import time
from dateutil.relativedelta import relativedelta
from dateutil import tz as dttz

def calc_next_start(current_start_ts, event_conf):
    # This calculates when the same event should happen next (Daily, Weekly, etc)
    local_tz = dttz.gettz(event_conf.get("timezone", "UTC"))
    dt = datetime.datetime.fromtimestamp(current_start_ts, tz=local_tz)
    rec = event_conf.get("recurrence_type", "once")

    if rec == "daily":
        dt += datetime.timedelta(days=1)
    elif rec == "weekly":
        dt += datetime.timedelta(weeks=1)
    elif rec == "biweekly":
        dt += datetime.timedelta(weeks=2)
    elif rec == "weekdays":
        dt += datetime.timedelta(days=1)
        while dt.weekday() >= 5:
            dt += datetime.timedelta(days=1)
    elif rec == "weekends":
        # Fires on Sat and Sun
        dt += datetime.timedelta(days=1)
        while dt.weekday() < 5:
            dt += datetime.timedelta(days=1)
    elif rec == "monthly":
        dt += relativedelta(months=1)
    elif rec == "custom":
        raw_cust = event_conf.get("custom_days") or ""
        try:
            # Format: "0,2,4" for Mon, Wed, Fri
            days = sorted([int(x.strip()) for x in str(raw_cust).split(",") if x.strip().isdigit()])
            if not days:
                return None
            
            curr_wd = dt.weekday()
            next_wd = None
            for d in days:
                if d > curr_wd:
                    next_wd = d
                    break
            
            if next_wd is not None:
                diff = next_wd - curr_wd
                dt += datetime.timedelta(days=diff)
            else:
                # Wrap to next week
                diff = (7 - curr_wd) + days[0]
                dt += datetime.timedelta(days=diff)
        except Exception:
            return None
    elif rec == "relative":
        raw_rel = event_conf.get("relative_combo") or ""
        try:
            # Format: "wk_first,day_monday"
            parts = [p.strip() for p in str(raw_rel).split(",") if p.strip()]
            wk = next((p for p in parts if p.startswith("wk_")), None)
            day = next((p for p in parts if p.startswith("day_")), None)
            
            if not wk or not day:
                return None
                
            day_map = {
                "day_monday": 0, "day_tuesday": 1, "day_wednesday": 2,
                "day_thursday": 3, "day_friday": 4, "day_saturday": 5, "day_sunday": 6
            }
            wd = day_map.get(day)
            if wd is None: return None
            
            # Move to next month first
            target_month = dt + relativedelta(months=1)
            
            from dateutil.relativedelta import MO, TU, WE, TH, FR, SA, SU
            wd_obj_list = [MO, TU, WE, TH, FR, SA, SU]
            wd_obj = wd_obj_list[wd]
            
            if wk == "wk_first":
                dt = target_month + relativedelta(day=1, weekday=wd_obj(1))
            elif wk == "wk_second":
                dt = target_month + relativedelta(day=1, weekday=wd_obj(2))
            elif wk == "wk_third":
                dt = target_month + relativedelta(day=1, weekday=wd_obj(3))
            elif wk == "wk_fourth":
                dt = target_month + relativedelta(day=1, weekday=wd_obj(4))
            elif wk == "wk_last":
                dt = target_month + relativedelta(day=31, weekday=wd_obj(-1))
            else:
                return None
        except Exception:
            return None
    else:
        return None
    return dt.timestamp()

def format_ts_utc(ts):
    """Format timestamp to YYYYMMDDTHHMMSSZ (UTC)."""
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def get_google_calendar_url(title, description, start_ts, end_ts=None):
    """Generate a Google Calendar event template URL."""
    base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
    
    params = {
        "text": title,
        "details": description,
    }
    
    start_str = format_ts_utc(start_ts)
    if end_ts:
        end_str = format_ts_utc(end_ts)
    else:
        # Default to 1 hour if no end time
        end_str = format_ts_utc(start_ts + 3600)
    
    params["dates"] = f"{start_str}/{end_str}"
    
    return f"{base_url}&{urllib.parse.urlencode(params)}"

def get_outlook_calendar_url(title, description, start_ts, end_ts=None):
    """Generate an Outlook.com / Office 365 calendar compose URL."""
    base_url = "https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose&rru=addevent"
    
    # Outlook uses slightly different param names and format
    start_dt = datetime.datetime.fromtimestamp(start_ts, tz=datetime.timezone.utc)
    start_str = start_dt.isoformat()
    
    if end_ts:
        end_dt = datetime.datetime.fromtimestamp(end_ts, tz=datetime.timezone.utc)
    else:
        end_dt = start_dt + datetime.timedelta(hours=1)
    end_str = end_dt.isoformat()

    params = {
        "subject": title,
        "body": description,
        "startdt": start_str,
        "enddt": end_str
    }
    
    return f"{base_url}&{urllib.parse.urlencode(params)}"

def get_yahoo_calendar_url(title, description, start_ts, end_ts=None):
    """Generate a Yahoo Calendar event template URL."""
    base_url = "https://calendar.yahoo.com/?v=60&view=d&type=20"
    
    start_str = format_ts_utc(start_ts)
    if end_ts:
        end_str = format_ts_utc(end_ts)
    else:
        end_str = format_ts_utc(start_ts + 3600)
        
    params = {
        "title": title,
        "desc": description,
        "st": start_str,
        "et": end_str
    }
    
    return f"{base_url}&{urllib.parse.urlencode(params)}"

def generate_ics_batch(events_list, limit_days=90, max_occurrences=10):
    """Creates a multi-event .ics file content as a string."""
    now = time.time()
    cutoff = now + (limit_days * 86400)
    
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Discord Event Bot//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]
    
    for ev in events_list:
        title = ev.get("title", "Event")
        # ICS requires escaping backslashes and newlines
        desc = (ev.get("description") or "").replace("\\", "\\\\").replace("\n", "\\n")
        start_ts = ev.get("start_time")
        if start_ts is None:
            continue
            
        duration = 3600
        if ev.get("end_time"):
            duration = float(ev["end_time"]) - float(start_ts)
            
        # Handle occurrences
        current_occurrence = 0
        current_start = float(start_ts)
        rec_type = (ev.get("recurrence_type") or "once").lower()
        
        while current_start < cutoff and current_occurrence < max_occurrences:
            current_end = current_start + duration
            
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{ev['event_id']}_{current_occurrence}@discord-event-bot",
                f"DTSTAMP:{format_ts_utc(now)}",
                f"DTSTART:{format_ts_utc(current_start)}",
                f"DTEND:{format_ts_utc(current_end)}",
                f"SUMMARY:{title}",
                f"DESCRIPTION:{desc}",
                "END:VEVENT"
            ])
            
            if rec_type in ["once", "none", ""]:
                break
                
            next_ts = calc_next_start(current_start, ev)
            if not next_ts or next_ts <= current_start:
                break
            current_start = next_ts
            current_occurrence += 1
            
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) # ICS standard uses CRLF
