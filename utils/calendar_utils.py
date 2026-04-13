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
    elif rec == "weekdays":
        dt += datetime.timedelta(days=1)
        while dt.weekday() >= 5:
            dt += datetime.timedelta(days=1)
    elif rec == "monthly":
        dt += relativedelta(months=1)
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
