#!/usr/bin/env python3
"""LettuceMeet agent helper — create and fill availability polls via the LettuceMeet GraphQL API."""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date

API_URL = "https://api.lettucemeet.com/graphql"
POLL_BASE_URL = "https://lettucemeet.com/l"


def graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    if "errors" in data:
        for err in data["errors"]:
            print(f"GraphQL error: {err['message']}", file=sys.stderr)
        sys.exit(1)
    return data["data"]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

CREATE_EVENT = """
mutation CreateEventMutation($input: CreateEventInput!) {
  createEvent(input: $input) {
    event { id title pollDates pollStartTime pollEndTime timeZone }
  }
}
"""


def cmd_create(args):
    dates = args.dates if args.dates else []
    if args.dates_from and args.dates_to:
        dates = _weekdays_between(args.dates_from, args.dates_to)

    if not dates:
        print("Error: provide --dates or both --dates-from and --dates-to", file=sys.stderr)
        sys.exit(1)

    # pollStartTime / pollEndTime are stored by LettuceMeet as-is (the clock
    # value is used directly for display without timezone conversion), so pass
    # local wall-clock time with a Z suffix.
    data = graphql(CREATE_EVENT, {
        "input": {
            "title": args.title,
            "pollStartTime": f"{args.start}:00Z",
            "pollEndTime": f"{args.end}:00Z",
            "maxScheduledDurationMins": args.duration,
            "timeZone": args.timezone,
            "pollDates": dates,
        }
    })
    event = data["createEvent"]["event"]
    url = f"{POLL_BASE_URL}/{event['id']}"
    print(f"Poll created: {url}")
    print(f"  id:    {event['id']}")
    print(f"  title: {event['title']}")
    print(f"  dates: {', '.join(event['pollDates'])}")
    print(f"  window: {event['pollStartTime'][:5]}–{event['pollEndTime'][:5]} ({event['timeZone']})")
    return event["id"]


# ---------------------------------------------------------------------------
# fill
# ---------------------------------------------------------------------------

CREATE_RESPONSE = """
mutation CreatePollResponseMutation($input: CreatePollResponseInput!) {
  createPollResponse(input: $input) {
    pollResponse { id availabilities { start end } }
  }
}
"""

UPDATE_RESPONSE = """
mutation UpdatePollResponseMutation($input: UpdatePollResponseInput!) {
  updatePollResponse(input: $input) {
    pollResponse { id availabilities { start end } }
  }
}
"""


def _parse_availabilities(raw: list[str]) -> list[dict]:
    """Parse 'YYYY-MM-DD HH:MM-HH:MM' strings into {start, end} dicts.

    Times are stored as naive UTC (same clock value as the local display time)
    because LettuceMeet renders the stored UTC time directly on the grid without
    applying a timezone offset.
    """
    blocks = []
    for entry in raw:
        parts = entry.strip().split()
        if len(parts) != 2:
            print(f"Bad availability entry (expected 'YYYY-MM-DD HH:MM-HH:MM'): {entry!r}", file=sys.stderr)
            sys.exit(1)
        d, time_range = parts
        s, e = time_range.split("-")
        blocks.append({
            "start": f"{d}T{s}:00Z",
            "end": f"{d}T{e}:00Z",
        })
    return blocks


def _filter_blocks(blocks: list[dict], min_hours: float, exclude_lunch: bool) -> list[dict]:
    result = []
    for b in blocks:
        s = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))

        if exclude_lunch:
            lunch_s = s.replace(hour=12, minute=0, second=0, microsecond=0)
            lunch_e = s.replace(hour=13, minute=0, second=0, microsecond=0)
            # Split around lunch if necessary
            if s < lunch_e and e > lunch_s:
                before_end = min(e, lunch_s)
                after_start = max(s, lunch_e)
                if (before_end - s).total_seconds() >= min_hours * 3600:
                    result.append({"start": b["start"], "end": _dt_to_z(before_end)})
                if e > lunch_e and (e - after_start).total_seconds() >= min_hours * 3600:
                    result.append({"start": _dt_to_z(after_start), "end": b["end"]})
                continue

        if (e - s).total_seconds() >= min_hours * 3600:
            result.append(b)

    return result


def _dt_to_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_fill(args):
    raw = args.availability
    if not raw and not sys.stdin.isatty():
        raw = [line.strip() for line in sys.stdin if line.strip()]
    if not raw:
        print("Error: provide availability via --availability or stdin", file=sys.stderr)
        sys.exit(1)

    blocks = _parse_availabilities(raw)
    blocks = _filter_blocks(blocks, min_hours=args.min_hours, exclude_lunch=args.exclude_lunch)

    if not blocks:
        print("No availability blocks remain after filtering.", file=sys.stderr)
        sys.exit(1)

    if args.response_id:
        data = graphql(UPDATE_RESPONSE, {
            "input": {"id": args.response_id, "availabilities": blocks}
        })
        resp = data["updatePollResponse"]["pollResponse"]
        print(f"Updated response {resp['id']} with {len(resp['availabilities'])} block(s)")
    else:
        data = graphql(CREATE_RESPONSE, {
            "input": {
                "eventId": args.event_id,
                "name": args.name,
                "email": args.email,
                "availabilities": blocks,
            }
        })
        resp = data["createPollResponse"]["pollResponse"]
        print(f"Created response {resp['id']} with {len(resp['availabilities'])} block(s)")
        print(f"  response_id: {resp['id']}")

    for b in resp["availabilities"]:
        s = b["start"][11:16]
        e = b["end"][11:16]
        d = b["start"][:10]
        print(f"  {d}  {s}–{e}")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

GET_EVENT = """
query EventQuery($id: ID!) {
  event(id: $id) {
    id title pollStartTime pollEndTime timeZone pollDates
    pollResponses {
      id
      user {
        __typename
        ... on AnonymousUser { name email }
        ... on User { id name email }
      }
      availabilities { start end }
    }
  }
}
"""


def cmd_get(args):
    data = graphql(GET_EVENT, {"id": args.event_id})
    event = data["event"]
    url = f"{POLL_BASE_URL}/{event['id']}"
    print(f"Poll: {url}")
    print(f"  title:  {event['title']}")
    print(f"  window: {event['pollStartTime'][:5]}–{event['pollEndTime'][:5]} ({event['timeZone']})")
    print(f"  dates:  {', '.join(event['pollDates'])}")
    for resp in event["pollResponses"]:
        u = resp["user"]
        name = u.get("name", "?")
        email = u.get("email", "")
        print(f"\n  Respondent: {name} <{email}>  (response_id: {resp['id']})")
        for b in resp["availabilities"]:
            s = b["start"][11:16]
            e = b["end"][11:16]
            d = b["start"][:10]
            print(f"    {d}  {s}–{e}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _weekdays_between(start: str, end: str) -> list[str]:
    """Return ISO date strings for weekdays in [start, end]."""
    d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    result = []
    while d <= end_d:
        if d.weekday() < 5:  # Mon–Fri
            result.append(d.isoformat())
        d += timedelta(days=1)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LettuceMeet agent helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a poll for next two weeks
  lettucemeet_agent.py create "Team sync" --dates-from 2026-06-29 --dates-to 2026-07-10

  # Fill your availability (blocks auto-filtered: >=1h, lunch excluded)
  lettucemeet_agent.py fill G8xXw --name "Rok" --email rok@example.com \\
    --availability "2026-06-29 13:00-14:00" "2026-06-29 15:00-17:00"

  # Or pipe availability from stdin
  echo "2026-06-29 13:00-17:00" | lettucemeet_agent.py fill G8xXw --name "Rok"

  # Update an existing response
  lettucemeet_agent.py fill G8xXw --response-id <id> \\
    --availability "2026-06-30 13:00-17:00"

  # Inspect a poll
  lettucemeet_agent.py get G8xXw
""",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new poll")
    p_create.add_argument("title", help="Poll title")
    p_create.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD", help="Explicit poll dates")
    p_create.add_argument("--dates-from", metavar="YYYY-MM-DD", help="Start of date range (weekdays only)")
    p_create.add_argument("--dates-to", metavar="YYYY-MM-DD", help="End of date range (weekdays only)")
    p_create.add_argument("--start", default="09:30", metavar="HH:MM", help="Poll window start (local, default: 09:30)")
    p_create.add_argument("--end", default="17:00", metavar="HH:MM", help="Poll window end (local, default: 17:00)")
    p_create.add_argument("--duration", type=int, default=60, metavar="MINS", help="Meeting duration in minutes (default: 60)")
    p_create.add_argument("--timezone", default="Europe/Zurich", help="Timezone (default: Europe/Zurich)")
    p_create.set_defaults(func=cmd_create)

    # fill
    p_fill = sub.add_parser("fill", help="Fill or update poll availability")
    p_fill.add_argument("event_id", help="Poll ID (e.g. G8xXw)")
    p_fill.add_argument("--name", required=True, help="Your display name")
    p_fill.add_argument("--email", default="", help="Your email (optional)")
    p_fill.add_argument(
        "--availability", nargs="+", metavar="'YYYY-MM-DD HH:MM-HH:MM'",
        help="Available windows (can also be piped via stdin)"
    )
    p_fill.add_argument("--response-id", metavar="ID", help="Existing response ID to update instead of creating new")
    p_fill.add_argument("--min-hours", type=float, default=1.0, help="Minimum contiguous window in hours (default: 1.0)")
    p_fill.add_argument("--no-exclude-lunch", dest="exclude_lunch", action="store_false", help="Keep 12:00-13:00 slots")
    p_fill.set_defaults(func=cmd_fill, exclude_lunch=True)

    # get
    p_get = sub.add_parser("get", help="Inspect a poll and its responses")
    p_get.add_argument("event_id", help="Poll ID")
    p_get.set_defaults(func=cmd_get)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
