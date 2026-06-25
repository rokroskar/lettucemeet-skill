---
name: lettucemeet
description: Create LettuceMeet scheduling polls and pre-fill availability from Google Calendar. Use when asked to make a meeting poll, share availability, or schedule something via LettuceMeet.
allowed-tools: Bash(python3 *)
---

# LettuceMeet

Use this skill to create a LettuceMeet poll and pre-fill the user's availability from their calendar.

## Helper

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py --help
```

## Key timezone quirk

LettuceMeet stores `pollStartTime`, `pollEndTime`, and availability datetimes as UTC, but **renders the stored clock value directly on the grid without applying any timezone offset**. This means:

- If you want the poll grid to show "09:30–17:00" in the user's local timezone, pass `--start 09:30 --end 17:00` (the helper appends `Z` for you).
- When submitting availability, express times as **local wall-clock times with a Z suffix**: if the user is free 10:00–12:00 CEST, submit `2026-06-29T10:00:00Z` (not `2026-06-29T08:00:00Z`).
- The `--availability` argument format `'YYYY-MM-DD HH:MM-HH:MM'` uses local time — the helper handles the formatting.

## Workflow

### 1. Understand the request

Ask for (or infer from context):
- **Title** of the poll
- **Date range** (e.g. "next 2 weeks", "Jun 29 – Jul 10")
- **Window** (default: 09:30–17:00 local)
- **Meeting duration** (default: 60 min)
- **Name / email** for the availability response

### 2. Check calendar availability

If the `mcp__claude_ai_Google_Calendar__list_events` tool is available, fetch the user's events for the date range:

```
list_events(startTime="YYYY-MM-DDT09:30:00", endTime="YYYY-MM-DDT17:00:00", timeZone="Europe/Zurich", orderBy="startTime")
```

Then compute free windows:
- Skip weekends
- Treat events with `transparency: transparent` as free
- Treat events with `status: cancelled` or declined (`responseStatus: declined`) as free
- Treat all-day events as blocking the whole day
- Default: exclude 12:00–13:00 lunch
- Default: only keep contiguous free windows ≥ 1 hour
- Skip days with no qualifying free windows (don't include them in `--dates`)

### 3. Create the poll

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py create "My poll title" \
  --dates-from 2026-06-29 --dates-to 2026-07-10 \
  --start 09:30 --end 17:00 --duration 60
```

Or with explicit dates (only days that have free time):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py create "My poll title" \
  --dates 2026-06-29 2026-06-30 2026-07-01 ...
```

The command prints the poll URL and ID.

**Note:** The poll title cannot be changed after creation (the update mutation requires auth). If the user wants to rename it, delete and recreate.

### 4. Pre-fill availability

Pass the free windows as `YYYY-MM-DD HH:MM-HH:MM` (local time). The helper automatically:
- Filters out windows < 1 hour (`--min-hours 1.0`)
- Excludes 12:00–13:00 lunch (pass `--no-exclude-lunch` to skip)
- Splits windows that straddle lunch into two blocks

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py fill <POLL_ID> \
  --name "Rok" --email rok.roskar@datascience.ch \
  --availability \
    "2026-06-29 13:00-17:00" \
    "2026-06-30 09:30-12:00" \
    "2026-06-30 14:00-17:00"
```

The command prints the response ID — save it if the user might want to update later.

### 5. Update availability

If the user wants to adjust (e.g. cut lunch, trim windows, add/remove days):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py fill <POLL_ID> \
  --response-id <RESPONSE_ID> \
  --availability "2026-06-29 13:00-17:00" ...
```

### 6. Inspect the poll

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lettucemeet_agent.py get <POLL_ID>
```

## Common adjustments

| User says | What to do |
|-----------|-----------|
| "cut lunch" | Re-run `fill` without `--no-exclude-lunch` (default) |
| "only keep 1h+ windows" | `--min-hours 1` (default); change as needed |
| "start at 10" | Recreate poll with `--start 10:00` |
| "add next Monday" | `get` the poll dates, recreate with the extra date, `fill` again |
| "rename it" | Cannot rename; recreate with new title and re-fill availability |
| "share the link" | `https://lettucemeet.com/l/<POLL_ID>` |

## Safety

- No authentication is required for creating polls or submitting responses.
- Polls and responses are anonymous by default; email is optional.
- Do not include personal health, financial, or NDA-covered information in poll titles.
- Never hardcode credentials; there are none needed for this API.
