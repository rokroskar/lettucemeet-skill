# LettuceMeet Skill

An agent skill for creating [LettuceMeet](https://lettucemeet.com) scheduling polls and pre-filling availability from Google Calendar.

No API key or account required — LettuceMeet allows anonymous poll creation and responses.

## Features

- Create polls from a date range or explicit dates
- Pre-fill your availability from Google Calendar (via MCP)
- Automatically excludes lunch (12:00–13:00) and sub-hour windows
- Update or inspect existing poll responses
- Handles LettuceMeet's timezone rendering quirk correctly

## Usage

Once installed, ask your agent in plain language:

```
Make a LettuceMeet poll called "Project sync meeting" for the next 2 weeks, 9:30-17:00, and pre-fill my availability from my calendar
```

```
Update the poll to cut lunch and only keep 1-hour minimum windows
```

```
Share the link to the LettuceMeet poll
```

## Installation

```bash
# From this directory
pi install .

# Or directly
pi install github:rokroskar/lettucemeet-skill
```

## Direct helper usage

```bash
python3 skills/lettucemeet/scripts/lettucemeet_agent.py --help
python3 skills/lettucemeet/scripts/lettucemeet_agent.py create "My poll" --dates-from 2026-06-29 --dates-to 2026-07-10
python3 skills/lettucemeet/scripts/lettucemeet_agent.py fill <POLL_ID> --name "Rok" --availability "2026-06-29 13:00-17:00"
python3 skills/lettucemeet/scripts/lettucemeet_agent.py get <POLL_ID>
```
