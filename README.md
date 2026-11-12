# Secret Santa Discord Bot

This bot runs a Secret Santa draw through Discord slash commands. Draw settings
are configured interactively for each draw and are not stored between draws.

## Setup

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
DISCORD_BOT_TOKEN=your_bot_token
```

Start the bot:

```powershell
python .\SecretSanta.py
```

The bot application must have the `bot` and `applications.commands` OAuth
scopes. Enable the Server Members Intent in the Discord Developer Portal.

## Running a draw

1. Run `/secretsanta` in the server.
2. Choose a participant role from the role selector.
3. Use **Add external user** to add participants outside the server by numeric
   Discord user ID and enter the nickname the bot should use for that person.
4. Use **Add exclusion pair** to prevent two participants from being assigned
   to each other. Both users must be in the current draw.
5. Choose **Start draw**.
6. Every participant receives their assignment by direct message.

The `/circle` command follows the same setup flow but requires all assignments
to form one single cycle.

Assignments are generated only when the draw starts. No users, roles,
exclusions, or assignments are hardcoded or persisted between draws.

## Requirements and limitations

- The selected role must contain at least two non-bot members.
- External users must be resolvable by Discord and must allow DMs from the bot.
- External-user nicknames are used in assignment messages and setup displays;
  the nickname does not change the user's Discord profile.
- External participants take part fully: they give to one person and receive
  from one person.
- If an assignment cannot satisfy the exclusions, the draw is rejected.
- A user who starts a setup is the only user allowed to control it.
- The bot does not store the bot token, participant data, or exclusion data in
  the repository.

## Testing

```powershell
pytest tests/ -v
```
