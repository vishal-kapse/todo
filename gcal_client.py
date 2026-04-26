#!/usr/bin/env python3
"""
Optional Google Calendar sync for generate_todo_pages.py (read-only).

One-time setup
--------------
1. Google Cloud Console (https://console.cloud.google.com/) → your project.
2. APIs & Services → Library → enable **Google Calendar API**.
3. APIs & Services → Credentials → **Create credentials** → **OAuth client ID**.
   - If asked, configure the OAuth consent screen (External + test users is enough for personal use).
   - Application type: **Desktop app** → create → **Download JSON**.
4. Save the file as::

     <credentials-dir>/client_secret.json

   Default credentials directory: ~/.config/todo-gcal/

5. Run::

     python3 generate_todo_pages.py --google-calendar

   A browser opens once; sign in with your **work Google account** and allow calendar read access.
   A **token.json** is saved beside client_secret.json for later runs (no browser until it expires).

Which calendar
--------------
* ``--gcal-calendar-id primary`` (default) is the primary calendar of the signed-in account.
* Use another calendar’s ID from Calendar settings → **Integrate calendar** (often an email-like string).

Dependencies::

    pip install -r requirements-google.txt
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Must match WORK TIMELINE grid in generate_todo_pages.py (7:00–22:00, 15 one-hour slots).
TIMELINE_START_HOUR = 7
TIMELINE_SPAN_HOURS = 15


@dataclass(frozen=True)
class GCalEvent:
    start: datetime
    end: datetime
    summary: str


@dataclass(frozen=True)
class TimelineSegment:
    """Event slice in hours from 07:00 local on the printed page date, clipped to [0, 15]."""

    start_h: float
    end_h: float
    title: str


def default_local_tz() -> datetime.tzinfo:
    """Best-effort local timezone for interpreting/printing day boundaries."""
    now = datetime.now().astimezone()
    if now.tzinfo is not None:
        return now.tzinfo
    return timezone.utc


def resolve_timezone(name: str | None) -> datetime.tzinfo:
    if name:
        try:
            return ZoneInfo(name)
        except Exception as exc:
            raise ValueError(f"Invalid IANA timezone {name!r}") from exc
    return default_local_tz()


def get_credentials(credentials_dir: Path) -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials_dir.mkdir(parents=True, exist_ok=True)
    token_path = credentials_dir / "token.json"
    secret_path = credentials_dir / "client_secret.json"
    if not secret_path.exists():
        raise FileNotFoundError(
            f"Missing OAuth client file: {secret_path}\n"
            "Download a Desktop OAuth client JSON from Google Cloud Console and save it there. "
            "See the module docstring at the top of gcal_client.py."
        )

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _parse_event_times(
    item: dict[str, Any], tz: datetime.tzinfo
) -> tuple[datetime, datetime] | None:
    s_raw = item.get("start") or {}
    e_raw = item.get("end") or {}

    if "dateTime" in s_raw and "dateTime" in e_raw:
        s = _parse_rfc3339_local(s_raw["dateTime"], tz)
        e = _parse_rfc3339_local(e_raw["dateTime"], tz)
        return s, e

    if "date" in s_raw and "date" in e_raw:
        d0 = date.fromisoformat(s_raw["date"])
        d1 = date.fromisoformat(e_raw["date"])
        start = datetime.combine(d0, time.min, tzinfo=tz)
        end = datetime.combine(d1, time.min, tzinfo=tz)
        return start, end

    return None


def _parse_rfc3339_local(s: str, fallback_tz: datetime.tzinfo) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=fallback_tz)
    return dt.astimezone(fallback_tz)


def fetch_events_range(
    first_day: date,
    last_day: date,
    calendar_id: str,
    credentials_dir: Path,
    tz: datetime.tzinfo,
) -> list[GCalEvent]:
    from googleapiclient.discovery import build

    creds = get_credentials(credentials_dir)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    time_min = datetime.combine(first_day, time.min, tzinfo=tz)
    time_max = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=tz)

    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    out: list[GCalEvent] = []
    for item in items:
        times = _parse_event_times(item, tz)
        if times is None:
            continue
        start, end = times
        summary = (item.get("summary") or "").strip() or "(no title)"
        out.append(GCalEvent(start=start, end=end, summary=summary))
    return out


def segments_for_print_day(
    events: list[GCalEvent],
    day: date,
    tz: datetime.tzinfo,
) -> list[TimelineSegment]:
    """Clip events to this local calendar day and to the printable 07:00–22:00 band."""
    day_lo = datetime.combine(day, time(TIMELINE_START_HOUR, 0), tzinfo=tz)
    day_hi = day_lo + timedelta(hours=TIMELINE_SPAN_HOURS)
    out: list[TimelineSegment] = []
    for ev in events:
        s = ev.start.astimezone(tz)
        e = ev.end.astimezone(tz)
        s = max(s, day_lo)
        e = min(e, day_hi)
        if e <= s:
            continue
        t0 = (s - day_lo).total_seconds() / 3600.0
        t1 = (e - day_lo).total_seconds() / 3600.0
        out.append(TimelineSegment(start_h=t0, end_h=t1, title=ev.summary))
    out.sort(key=lambda seg: (seg.start_h, seg.end_h))
    return out
