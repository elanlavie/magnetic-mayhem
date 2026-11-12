# 🕵️ Imposter

Explore a damaged space station, run cargo relays, talk science with the ship engineer, and restore its systems. Play solo, cooperate with a crew, or race another team.

## 🧠 Claude Sonnet is always on

Every tutor conversation—solo, bot practice, or multiplayer—uses `claude-sonnet-5-5` through the Python server. There is no AI-off setting, keyword tutor, or offline game mode. API errors preserve progress and ask the player to retry; they never switch to scripted feedback. Existing rooms from the earlier version also use Sonnet after upgrading.

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

## 🕵️ Imposter missions

In Mission control, choose **Imposter mission** (the default), select 1–3 imposters,
1–7 science conversations per crewmate, and separate discussion/voting durations.
New rooms begin in a lobby. Students join before the teacher clicks **Assign roles
& start round**. Minimum players: 4 for one imposter, 7 for two, 10 for three.
Automatic fun names remain available. Teachers can remove lobby participants and
end or restart rounds. Teacher-only role spoilers should stay off the projector.

- Crewmates win by finishing every assigned Sonnet conversation (including ghost
  tasks) or by voting out all imposters. These conversations are the actual tasks;
  collecting cells and installing repairs are not required in this mode.
- Imposters have real science conversations as cover, but their practice does not
  advance the crew task bar. They win by reaching parity with the living crew or
  by letting a reactor sabotage expire.
- Imposters can tag nearby crewmates with clear line of sight, but each tag must be
  powered up by finishing real science conversations (default 2, teacher-adjustable
  from 1 to 5; every correct conversation counts, including repeats). A 30-second
  cooldown also applies at round start, after a tag, and after meetings. Tags are
  non-graphic. Solo bot imposters simulate this by "studying" before they tag.
- **Shields:** once a crewmate has finished their assigned tasks, each extra correct
  conversation earns a shield (maximum 2). A shield blocks one tag attempt: the
  crewmate is told someone nearby tried to tag them, the imposter is told the tag was
  blocked (and gets a shorter cooldown), and nobody is eliminated. Shield counts are
  private. Extra conversations never advance the crew task bar.
- Living players can report nearby downed explorers. Each living player also gets
  one emergency meeting, called at the arrival pad, with a shared cooldown.
- **Meetings never interrupt a conversation.** Reports and emergency meetings open a
  non-blocking meeting: students keep chatting and moving, a banner shows the time
  left, and the ballot appears when a student finishes or leaves their current chat
  (they can also choose "Vote later"). Voting is rejected mid-chat. The defaults are a
  **30 second discussion period** (before ballots open) and a **90 second voting
  window**; teachers can change both and optionally enable written in-game discussion. Ghosts observe without speaking in written chat or voting.
  Ties, skip votes, and missing ballots do not force an ejection. Ballots are locked
  after submission. Individual choices stay private during the meeting; aggregate
  tallies appear afterward. Roles remain secret until the round ends.
- Reactor sabotage gives 90 seconds to stabilize two panels, at Motors and
  Generators. Any living player can help. Reports pause the reactor timer during
  meetings; the teacher's pause freezes round deadlines and cooldowns.
- Tagged and voted-out players become ghosts and can keep learning. Ghost
  crewmates still contribute tasks; ghosts cannot intervene in the round.
- Winning a round and academic progress are separate. Practice never awards the
  same academic points twice. Assigned conversations can count for a new round
  even when the underlying concept was completed in an earlier round.

**Solo bot practice:** Study solo offers an imposter practice game with five
computer-controlled players, with a choice of crewmate, imposter, or random role.
Bots navigate walls, simulate time spent doing tasks, tag, sabotage, repair,
report, and vote. Crew bots vote from what they observed; otherwise they skip.
They are explicitly labeled bots. Their task completion is game simulation, not
AI grading or evidence of student understanding. The human's science conversation
always goes to Claude Sonnet. Bot meetings include written NPC comments so solo
players can participate. Solo exploration remains available as a separate choice.

The tutor also occasionally uses “Let the equation guide your thinking!”,
“Yum Fysicz!”, and “Good Energy!” where they fit.

## 🏫 Classes, sign-in and safety

With `AUTH_MODE=classes`, students and teachers sign in with Google. Teachers create classes (restricted to student email domains), share expiring invite links, and can read every chat in their classes. Each student gets a class nickname: the AI suggests one from the Google name, the teacher edits and saves it, and future sign-ins use it. For each game the teacher chooses real class nicknames or anonymous fun names (only the teacher can see who is who). Messages about self-harm, harm to others or inappropriate language raise an alert (tutor classification plus a keyword backstop) shown on the teacher dashboard and emailed with a link to the chat. See DEPLOY.md.

**Private question library.** Teachers can import a test or study guide (TXT, PDF, DOCX or pasted text). The AI turns every question, including multiple-choice, into an explain-your-reasoning question tagged by topic and saves it under that teacher's account only (never in the repo). In setup, pick sets and topic tags, for example just "Magnetism", to build a mission.

## Hosting

Run a single instance behind HTTPS. The included `render.yaml` proposes one paid Python service with a 1 GB persistent disk. The existing production service is at https://imposter.elanlavie.net/ (Render address: https://magnetic-mayhem.onrender.com/). GitHub source: https://github.com/elanlavie/magnetic-mayhem.

SQLite stores rooms, conversations, progress, and relay records. Only files on the mounted disk survive deployment. Rooms load for up to seven days; expired records remain in the database. This prototype has a 40-player room cap, not a classroom load guarantee. It has no school identity system or automatic application-level API budget. Use nicknames and manage retention appropriately. Live curriculum and messages go to Anthropic.

## Verification

Run `python3 -m unittest discover -s tests -v` and `node tests/client-smoke.cjs`.

The 58-test backend suite covers hidden roles, private ballots, bot navigation, classroom and written meetings, tags, sabotage, ghost learning, restart recovery, plus always-on AI (including legacy rooms), provider failure without fallback, scoring, retries, concurrent replies while leaving, saved conversations, assigned names, relay validation and rewards, restart recovery, and multiplayer rules. Client checks cover onboarding, Enter / Shift+Enter / IME input, automatic countdowns, Escape, backdrop dismissal, and saved drafts. Chrome verification additionally exercises actual controls and rendering; the local UI fixture is separate from the production build. Real Sonnet integration is verified on the deployed service.
