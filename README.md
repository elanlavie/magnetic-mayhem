# 🧲 Magnetic Mayhem

Explore a damaged space station, run cargo relays, talk science with the ship engineer, and restore its systems. Play solo, cooperate with a crew, or race another team.

## 🧠 Claude Sonnet is always on

Every tutor conversation—solo or multiplayer—uses `claude-sonnet-5-5` through the Python server. There is no AI-off setting, keyword tutor, or offline game mode. API errors preserve progress and ask the player to retry; they never switch to scripted feedback. Existing rooms from the earlier version also use Sonnet after upgrading.

Configure these environment variables on the server:

- `ANTHROPIC_API_KEY`: Anthropic API key, stored only in hosting secrets.
- `ANTHROPIC_MODEL`: `claude-sonnet-5-5`.
- `TEACHER_KEY`: private code for teacher session creation and curriculum tools.
- `GAME_DB`: persistent SQLite file path, such as `/var/data/game.sqlite3`.
- `PORT`: supplied by the host, or 8000 locally.

Set the variables in your shell or hosting environment, install `requirements.txt`, and run `python3 server.py`. The app does not automatically read a `.env` file. Python 3.10+ is recommended. Open the hosted website rather than downloading its HTML.

Solo mode uses live AI automatically; no teacher code is required for a public solo expedition. API usage is billed to the configured Anthropic account. Teacher study codes optionally select the class curriculum and settings. Teacher controls remain access-code protected. The provider key is never sent to the browser.

## 🎮 The adventure

The goal is to restore all systems. Choose your own route:

- **Move and dash:** WASD or arrows; hold Space for a rechargeable burst. Touch controls are provided.
- **Run supplies:** start a relay at the arrival pad, follow glowing cargo checkpoints, then return home. Three routes have saved personal best times. First completion of each route gives 2 energy cells; repeat runs improve your time without farming rewards. Aim for 20 seconds; slower runs still complete.
- **Explore:** walk over floating energy cells. Each explorer has their own supplies.
- **Talk science:** press E near a station. Enter sends a message; Shift+Enter adds a line. The clue button is free.
- **Leave freely:** Escape, the visible close button, or a click outside closes a conversation. Your messages, attempts, and draft are preserved. You can visit another station and return later, even while an earlier AI reply finishes.
- **Earn rewards:** each newly completed explanation gives one energy cell. Academic points retain the original 1 / 0.5 / 0.25 scoring and supported-revision rules. Relays do not add academic points.
- **Repair:** finish a station’s conversations, then spend 2 cells near it to install the repair. Restored rooms light up. Complete all repairs for the certificate.

Rules appear on a new expedition and remain available from the Rules button. Follow-up countdowns start automatically after feedback, default to 30 seconds, and never exceed 30 seconds. Expiry does not submit or deduct points. Relaxed solo mode removes the countdown without turning off AI.

## 🛠️ Teacher sessions

Open Mission control, enter the teacher access code, review the topic pack, and create a room. Claude is always enabled. The teacher can enable automatic fun names (on by default in setup); the server assigns unique names and ignores student-supplied names in those rooms. Names remain stable across reconnects and restarts. The teacher can alternatively allow preferred names.

Choose co-op or two-team race and optionally allow independent solo study using the room code. The dashboard tracks explanations and repairs. TXT/Markdown/JSON imports are built in; PDF and DOCX text extraction use the dependencies in `requirements.txt`. Review AI-generated questions and reference answers before classroom use.

## Hosting

Run a single instance behind HTTPS. The included `render.yaml` proposes one paid Python service with a 1 GB persistent disk. The existing production service is at https://magnetic-mayhem.onrender.com/. GitHub source: https://github.com/elanlavie/magnetic-mayhem.

SQLite stores rooms, conversations, progress, and relay records. Only files on the mounted disk survive deployment. Rooms load for up to seven days; expired records remain in the database. This prototype has a 40-player room cap, not a classroom load guarantee. It has no school identity system or automatic application-level API budget. Use nicknames and manage retention appropriately. Live curriculum and messages go to Anthropic.

## Verification

Run `python3 -m unittest discover -s tests -v` and `node tests/client-smoke.cjs`.

The backend suite covers always-on AI (including legacy rooms), provider failure without fallback, scoring, retries, concurrent replies while leaving, saved conversations, assigned names, relay validation and rewards, restart recovery, and multiplayer rules. Client checks cover onboarding, Enter / Shift+Enter / IME input, automatic countdowns, Escape, backdrop dismissal, and saved drafts. Chrome verification additionally exercises actual controls and rendering; the local UI fixture is separate from the production build. Real Sonnet integration is verified on the deployed service.
