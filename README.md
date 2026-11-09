# 🚀 Magnetic Mayhem

A first playable version of a full-movement conceptual learning game for ninth-grade students. Explore a shared station, collect energy cells, explain your thinking to NOVA, and repair systems. Includes solo study, cooperative multiplayer, and a two-team race.

## Try it immediately

Open **Magnetic_Mayhem_Demo.html** in a browser. This self-contained file supports **solo movement and scripted magnetism practice** without installing anything. Download it first if your file viewer does not run interactive HTML.

The demo tutor checks keywords; it is not an AI chatbot and must not be used to assess students. It can reject valid explanations and accept an incorrect explanation containing the expected words. Live mode replaces that checklist with AI evaluation, which still needs teacher oversight.

## Run the full website

Requires Python 3.10 or later. No dependencies are needed for the built-in curriculum and multiplayer demo.

1. Unzip this project.
2. In a terminal, change into the `magnetic-mayhem` folder.
3. Run:

```sh
python3 server.py
```

4. Open **http://localhost:8000** on that computer.

On Windows, use `py server.py` if `python3` is unavailable. Students need a reachable hosted server or the server computer's LAN address, not `localhost` on their own devices. Everyone must connect to the same server. A downloaded HTML file alone does not provide multiplayer.

## Enable the real AI tutor

This implementation defaults to **Claude Sonnet 5.5** through the Claude Messages API on the Python server. It uses medium effort and no up-front thinking for short, responsive tutoring exchanges. The API credential remains on the server and is never included in browser code.

Set environment variables before starting the server:

```sh
export ANTHROPIC_API_KEY='your-api-key'
export ANTHROPIC_MODEL='claude-sonnet-5-5'
export TEACHER_KEY='choose-a-private-teacher-access-code'
python3 server.py
```

These are shell environment variables; the application does not automatically load a `.env` file. For a hosted service, set them in its environment settings instead. API usage is billed separately by the provider. Set spending limits with your provider and share the teacher code only with authorized teachers. Model availability varies by account; replace the model identifier if needed.

In **Mission control**, enable **Use live AI tutor** and enter the teacher access code. A server with a live AI key requires a teacher code to create AI sessions. Students only need a room/study code. Direct solo launch without a teacher-approved code uses the built-in demo tutor, even when the server has a live key.

The live network call could not be exercised in this build environment because no API credential was supplied. AI failure recovery and grading response handling were tested with mocked responses.

## Teacher workflow

1. Choose **Mission control**.
2. Keep the built-in magnetism pack, or paste topics / import a guide.
3. For new material, click **Create AI topic pack**. This requires live AI configuration.
4. Expand the topic preview to inspect every question and reference answer. The JSON editor lets you make exact changes; click **Apply edits** afterward.
5. Choose co-op or two-team race, first-response time, and follow-up time.
6. Choose whether the room code may also be used for solo study.
7. Launch, copy the join link, and show students the six-character room code.

Use **Export pack** to keep a reusable JSON file and save that pack in this browser's solo selector. JSON imports restore a pack without regenerating it. Arbitrary pasted topics are never silently assessed by the magnetism keyword checklist.

TXT and Markdown imports work directly. PDF and DOCX extraction use optional dependencies:

```sh
python3 -m pip install -r requirements.txt
```

Scanned image-only PDFs are not supported; paste readable text instead. Text imports are capped at 40,000 characters, files at 4 MB, and generated packs at 7 stations with 1–3 challenges each. This first version uses two challenges for each of the seven built-in magnetism topics: 14 explanations, not a fixed 15-question sequence.

## Student play

- **Move:** WASD or arrow keys; touch arrows on phones/tablets.
- **Interact:** E, or the on-screen interaction button, near a station.
- **Collect:** Walk over floating yellow energy cells. Every explorer has their own set, so faster players cannot take all the supplies.
- **Explain:** Complete the station's two conversations. Hints and clarification are free.
- **Repair:** Return with two cells and interact again to install the repair.
- **Boost:** After the first repair, hold Space while moving, or hold the touch lightning control and a direction.
- **Teamwork:** Repairs contribute to shared team system progress and give every teammate one energy cell. Individual understanding is tracked separately, so someone else's repair does not award you learning credit.
- **Race:** The two balanced teams compare distinct shared systems restored. There is no elimination or sabotage. The race does not lock out the other crew after a finish; everyone can complete the curriculum.
- **Finish:** Repair every system personally to earn the screenshot-ready certificate. Teachers can inspect each student's explanation count and repair progress in the dashboard.

The mission log lists stations and personal progress. Repaired stations offer optional practice when you revisit them. The current challenge must be completed before returning to movement; if stuck, request a hint or a worked explanation and revise the same idea. This is a first playable loop rather than a finished commercial game: no collision with other players, combat, inventory trading, audio, or animated NPC pathfinding.

## Solo study at home

Choose **Study solo**, enter a nickname, and optionally enter a teacher's study code. The code clones the selected teacher curriculum and AI setting into an independent solo session. Choose **Relaxed mode** to remove the countdown.

The teacher server must remain reachable for study codes and live tutoring. Server rooms last up to seven days across restarts. Progress is saved in SQLite; your browser keeps a return token for the most recent player session and the latest teacher dashboard. This is device/browser-specific, not an account synced across devices. Do not clear browser storage if you want to continue. Opening a new expedition replaces the browser's quick-resume link, but does not erase server history.

## Timer and assessment behavior

- Default: 30 seconds for an initial response, 60 for a follow-up.
- At zero, the student sees “Your next move?” and sentence starters. It never auto-submits or deducts points.
- Waiting for the AI and reading its feedback pause the timer. **Ready to respond** starts the next countdown; beginning to type also starts it.
- Switching tabs does not pause an active countdown. Refresh restores its deadline.
- Teacher pause affects the whole room. A student can pause their own view for an interruption.
- Correct explanations earn 1, 0.5, or 0.25 points depending on unsuccessful attempts. After three unsuccessful attempts or a requested worked solution, the original score is 0 and students repair their reasoning.
- Bare answers or vague explanations prompt follow-up without losing an attempt. API errors do not consume attempts. Repeated requests cannot award points twice.
- Repaired explanations unlock progress even when the original score is low. Optional practice never adds points twice.

The server stores scores and progression. Client timers are pacing tools, not cheat-proof timing or attendance measures. NOVA cannot know who is speaking or who controls the keyboard.

## Hosting and practical limits

A `Dockerfile` is included for a persistent single-instance Python service. Expose port 8000 (or set `PORT`) and put the service behind HTTPS. Keep `game.sqlite3` on a persistent volume using the `GAME_DB` environment variable. All browsers must reach the same instance; this prototype does not synchronize multiple server instances.

Room state uses short polling, with a maximum of 40 players per room. This cap is an implementation limit, not a verified classroom capacity: real classroom load, school filtering, mobile controls, and reconnects still require a pilot. There is no account system, administrative deletion UI, automatic API cost budget, or production abuse protection. Teacher creation is code-protected when live AI is enabled; room codes are lightweight invitations rather than school identity authentication.

Curriculum and student conversation text are sent to the configured AI provider in live mode. Use nicknames and avoid personal information. SQLite includes tutor conversations and student progress; manage that file according to your classroom retention needs. Unfinished rooms are retained in the database even after expiring from the active room list. Delete the database when the server is stopped to reset all rooms.

## Verification completed

- 22 Python tests: full built-in playthrough; scoring; duplicate submissions; free hints; supported revisions; API failures; teammate rewards; room pause; restart recovery; study codes; team assignment; private-state filtering.
- JavaScript syntax validation.
- Server-backed and standalone client simulations: setup, movement, encounters, timer expiry, feedback readiness, hints, scoring, return-to-map.
- The actual canvas drawing was rendered and visually inspected.

A real-browser automation run could not be completed because Chromium was unavailable and its download was blocked by the environment. The DOM/canvas simulation is not equivalent to Chrome/Safari testing. The interface is responsive and includes keyboard and touch controls, but actual device accessibility, mobile layout, and multiplayer classroom load remain to be verified.

Run the backend tests:

```sh
python3 -m unittest discover -s tests -v
```

The client simulation additionally needs Node and `@napi-rs/canvas`; see `tests/client-smoke.cjs`. Its dependency path uses the build environment's `CODEX_PRIMARY_RUNTIME_NODE_MODULES` variable and should be adapted for another machine.

## Files

- `server.py`: HTTP server, SQLite persistence, multiplayer state, file extraction, AI generation and tutor evaluation.
- `public/index.html`, `style.css`, `app.js`: responsive interface and canvas movement game.
- `public/curriculum.json`: built-in magnetism questions and scripted demo checks.
- `Magnetic_Mayhem_Demo.html`: bundled offline solo demo.
- `build_demo.py`: regenerate the single-file demo after interface changes.
- `tests/`: backend and client logic checks.

API reference used: https://platform.claude.com/docs/en/api/messages/create
