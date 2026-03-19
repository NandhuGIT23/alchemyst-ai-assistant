"""
calendar_service.py
-------------------
Fetches available demo slots from Google Calendar using the free/busy API.

Setup (one-time):
  1. Go to console.cloud.google.com → New Project
  2. Enable "Google Calendar API"
  3. Create credentials → Service Account → download JSON key
  4. Share your calendar with the service account email (give it "See all event details" permission)
  5. Set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_CALENDAR_ID in .env

Returns 3 available 30-min slots within the next 5 business days,
skipping weekends and existing busy times.
"""

import os
import json
import datetime
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # full JSON string
GOOGLE_CALENDAR_ID          = os.getenv("GOOGLE_CALENDAR_ID", "primary")
TIMEZONE                    = os.getenv("CALENDAR_TIMEZONE", "Asia/Kolkata")

# Demo slots are offered within these working hours (24h format)
WORK_START_HOUR = 9   # 9 AM
WORK_END_HOUR   = 17  # 5 PM
SLOT_DURATION   = 30  # minutes
SLOTS_TO_OFFER  = 3   # how many options to show the user

# Windows strftime doesn't support %-I; use %#I on Windows, %-I elsewhere
_HOUR_FMT = "%#I" if os.name == "nt" else "%-I"
_SLOT_FMT = f"%A %d %B at {_HOUR_FMT}:%M %p"


def _get_service():
    """Build Google Calendar API service from service account credentials."""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set in environment")

    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def get_available_slots(num_slots: int = SLOTS_TO_OFFER) -> list[dict]:
    """
    Returns a list of available 30-min demo slots for the next 5 business days.
    Each slot: { "label": "Tuesday 20 May at 3:00 PM", "iso_start": "2025-05-20T09:30:00+05:30" }
    Falls back to a static message if Calendar API is unavailable.
    """
    try:
        service = _get_service()
        tz      = pytz.timezone(TIMEZONE)
        now     = datetime.datetime.now(tz)

        # Query window: now → 7 days ahead
        time_min = now.isoformat()
        time_max = (now + datetime.timedelta(days=7)).isoformat()

        # Fetch busy periods
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": TIMEZONE,
            "items": [{"id": GOOGLE_CALENDAR_ID}],
        }
        result     = service.freebusy().query(body=body).execute()
        busy_times = result["calendars"][GOOGLE_CALENDAR_ID]["busy"]
        print(f"[calendar] Busy times: {busy_times}")

        busy_ranges = [
            (
                datetime.datetime.fromisoformat(b["start"]).astimezone(tz),
                datetime.datetime.fromisoformat(b["end"]).astimezone(tz),
            )
            for b in busy_times
        ]

        # Walk candidate slots day by day
        available = []
        day_offset = 0

        while len(available) < num_slots and day_offset < 14:
            day_offset += 1
            candidate_day = now + datetime.timedelta(days=day_offset)

            # Skip weekends
            if candidate_day.weekday() >= 5:
                continue

            # Walk through working hours in SLOT_DURATION increments
            slot_start = candidate_day.replace(
                hour=WORK_START_HOUR, minute=0, second=0, microsecond=0
            )
            slot_end_limit = candidate_day.replace(
                hour=WORK_END_HOUR, minute=0, second=0, microsecond=0
            )

            while slot_start < slot_end_limit and len(available) < num_slots:
                slot_end = slot_start + datetime.timedelta(minutes=SLOT_DURATION)

                # Check slot doesn't overlap any busy period
                is_busy = any(
                    not (slot_end <= busy_start or slot_start >= busy_end)
                    for busy_start, busy_end in busy_ranges
                )

                # Also skip slots in the past
                if not is_busy and slot_start > now:
                    available.append({
                        "label":     slot_start.strftime(_SLOT_FMT),
                        "iso_start": slot_start.isoformat(),
                    })

                slot_start = slot_end  # move to next slot

        return available

    except Exception as e:
        print(f"[calendar] Error fetching slots: {e}")
        # Graceful fallback — static placeholder slots
        return _fallback_slots()


def _fallback_slots() -> list[dict]:
    """
    Static fallback if Google Calendar is unavailable.
    Returns 3 placeholder slots starting from tomorrow.
    """
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.datetime.now(tz)
    slots = []
    offset = 1

    while len(slots) < SLOTS_TO_OFFER:
        day = now + datetime.timedelta(days=offset)
        offset += 1
        if day.weekday() >= 5:
            continue
        slot = day.replace(hour=10, minute=0, second=0, microsecond=0)
        slots.append({
            "label":     slot.strftime(_SLOT_FMT),
            "iso_start": slot.isoformat(),
        })

    return slots
