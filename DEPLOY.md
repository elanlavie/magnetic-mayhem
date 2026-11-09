# Production deployment

- Game: https://magnetic-mayhem.onrender.com/
- Source: https://github.com/elanlavie/magnetic-mayhem
- Render service: https://dashboard.render.com/web/srv-dboo7mvf3r2c73bqn0gg
- Server: Python, one instance in Oregon, `python server.py`.
- Build: `pip install -r requirements.txt`.
- Health check: `/api/config`.
- Disk: 1 GB at `/var/data`; `GAME_DB=/var/data/game.sqlite3`.
- Model: `claude-sonnet-5-5`. No scripted tutor or AI-off option.

Keep `ANTHROPIC_API_KEY` and `TEACHER_KEY` in Render's secret environment settings, never in GitHub. The API key created during setup expires December 9, 2026; replace it before that date. Funding and provider availability are required for live tutoring. If the API fails, attempts and progress remain intact.

The initial quoted hosting cost was $7/month compute plus $0.25/month disk, before API usage and any applicable additional charges. Review the current hosting invoice for actual charges.

A deployment restarts the single process. Saved rooms and progress load from SQLite. Back up SQLite using a consistent database backup rather than copying a file during a write. Never replace the production database with a local test database.

## Classroom mode (accounts, classes, safety alerts)

Set `AUTH_MODE=classes` to require Google sign-in. Leave it unset (or `off`) for an open demo deployment with no accounts, which is the one to share with friends and family. Run the two as **separate deployments**; students should only ever be given the classroom URL.

| Variable | Purpose |
|---|---|
| `AUTH_MODE` | `classes` to require sign-in; `off` (default) for the open demo |
| `GOOGLE_CLIENT_ID` | OAuth Web client ID from Google Cloud Console |
| `TEACHER_EMAILS` | Comma-separated emails that sign in as teachers |
| `TEACHER_DOMAINS` | Optional: every account on these domains is a teacher (e.g. your district domain). Only use if students are on a different domain |
| `OPEN_TEACHER_SIGNUP` | `1` lets any Google account become a teacher so other teachers can use the site. Anyone could then create classes; leave off unless you want that |
| `DEFAULT_STUDENT_DOMAINS` | Default student email domains for new classes (e.g. `wccschools.org`) |
| `PUBLIC_URL` | Public site address, used in invite links and alert emails |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_FROM` | Outgoing mail for safety alerts. Without these the dashboard still shows alerts and labels email as "not configured" |

### Google setup
1. Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → Web application.
2. Add your site address (for example `https://magnetic-mayhem.onrender.com`) under Authorized JavaScript origins.
3. OAuth consent screen: set publishing status to **In production**. In "Testing" only listed test users can sign in, so students would be blocked.
4. Put the client ID in `GOOGLE_CLIENT_ID`. If your district restricts third-party apps, ask IT to allow the client ID.

### Privacy notes
- Teachers can read every chat in their own classes; students are not told otherwise by this software, so tell them.
- Safety alert emails contain the student, class, category and a link to the chat. They never include the message text.
- Chats and accounts live in the SQLite database. Use a persistent disk on Render, or they are lost on redeploy.
