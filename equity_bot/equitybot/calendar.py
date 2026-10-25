from datetime import datetime, timezone
import pandas as pd
import exchange_calendars as xc

def calendar(name='XNYS'):
    return xc.get_calendar(name)

def completed_session(now=None, name='XNYS'):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError('now 必须含时区')
    cal = calendar(name)
    day = now.tz_convert('America/New_York').date().isoformat()
    s = cal.date_to_session(day, direction='previous')
    if cal.session_close(s) > now:
        s = cal.previous_session(s)
    return s.date().isoformat()

def sessions(end, count=61, name='XNYS'):
    cal = calendar(name)
    s = cal.date_to_session(end, direction='none')
    i = cal.sessions.get_loc(s)
    return [d.date().isoformat() for d in cal.sessions[i-count+1:i+1]]

def due(now, delay=75, name='XNYS'):
    cal = calendar(name)
    now = pd.Timestamp(now)
    day = now.tz_convert('America/New_York').date().isoformat()
    if not cal.is_session(day):
        return None
    close = cal.session_close(day)
    return day if now >= close + pd.Timedelta(minutes=delay) else None
