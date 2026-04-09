import urllib.parse
import datetime

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
