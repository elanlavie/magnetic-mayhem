# 🕵️ Imposter

Explore a damaged space station, run cargo relays, answer multiple-choice questions, and restore its systems. Play solo, cooperate with a crew, or race another team. There is no AI anywhere: teachers write or paste the questions, and every answer is graded instantly by the server.

## ❓ Multiple choice only

Every question has 2–5 choices and one correct answer, plus a short explanation that students read after answering. Choices are shuffled for each student. A student gets one try per question: a correct answer earns credit, a miss shows the explanation and earns nothing. (The earlier version with an AI tutor lives on the `tutor-chat-version` branch.)

Configure these environment variables on the server:

- `TEACHER_KEY`: private code for teacher session creation and curriculum tools.
- `GAME_DB`: persistent SQLite file path, such as `/var/data/game.sqlite3`.
- `PORT`: supplied by the host, or 8000 locally.

Set the variables in your shell or hosting environment, install `requirements.txt`, and run `python3 server.py`. The app does not automatically read a `.env` file. Python 3.10+ is recommended. Open the hosted website rather than downloading its HTML.

Solo mode needs no teacher code for a public solo expedition. Teacher study codes optionally select the class game.

## 🎮 The adventure

The goal is to restore all systems. Choose your own route:

- **Move and dash:** WASD or arrows; hold Space for a rechargeable burst. Touch controls are provided.
- **Run supplies:** start a relay at the arrival pad, follow glowing cargo checkpoints, then return home. Three routes have saved personal best times. First completion of each route gives 2 energy cells; repeat runs improve your time without farming rewards. Aim for 20 seconds; slower runs still complete.
- **Explore:** walk over floating energy cells. Each explorer has their own supplies.
- **Answer questions:** press E near a station, pick a choice, and submit. The server grades it instantly.
- **Leave freely:** Escape, the visible close button, or a click outside closes a question. You can visit another station and return later.
- **Earn rewards:** each correct answer gives one energy cell and a point. Relays do not add academic points.
- **Repair:** answer a station’s questions, then spend 2 cells near it to install the repair. Restored rooms light up. Complete all repairs for the certificate.

Rules appear on a new expedition and remain available from the Rules button. Countdowns default to 30 seconds. Expiry does not submit or deduct points. Relaxed solo mode removes the countdown.

## 🛠️ Teacher sessions

Open Mission control, paste your questions (see the format below), review them, and create a room. The teacher can enable automatic fun names (on by default in setup); the server assigns unique names and ignores student-supplied names in those rooms. Names remain stable across reconnects and restarts.

Choose co-op or two-team race and optionally allow independent solo study using the room code. The dashboard tracks answers and repairs. TXT/Markdown/JSON imports are built in; PDF and DOCX text extraction use the dependencies in `requirements.txt`.

### Writing questions

```
Topic: Magnets            (optional: starts a new room)
1. Which poles attract each other?
A) North and north
B) North and south
C) South and south
Answer: B
Explanation: Opposite poles attract.   (optional)
```

A `*` after the right choice also works in place of the `Answer:` line. Write two or three similar questions under each topic so classmates do not all get the same one. Questions missing an answer are skipped and reported.

## 🕵️ Imposter missions

In Mission control, choose **Imposter mission** (the default), select 1–3 imposters,
1–7 questions per crewmate, and separate discussion/voting durations.
New rooms begin in a lobby. Students join before the teacher clicks **Assign roles
& start round**. Minimum players: 4 for one imposter, 7 for two, 10 for three.
Automatic fun names remain available. Teachers can remove lobby participants and
end or restart rounds. Teacher-only role spoilers should stay off the projector.

- Crewmates win by answering every assigned question (including ghost
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
evidence of student understanding. Bot meetings include written NPC comments so solo
players can participate. Solo exploration remains available as a separate choice.

## 🏫 Classes, sign-in and safety

With `AUTH_MODE=classes`, students and teachers sign in with Google. Teachers create classes (restricted to student email domains), share expiring invite links, and can see every answer in their classes. Each student gets a class nickname: a first-name guess is filled in from the Google name, the teacher edits and saves it, and future sign-ins use it. For each game the teacher chooses real class nicknames or anonymous fun names (only the teacher can see who is who). Messages about self-harm, harm to others or inappropriate language raise an alert (tutor classification plus a keyword backstop) shown on the teacher dashboard and emailed with a link to the chat. See DEPLOY.md.

**Private question library.** Teachers can import a test or study guide (TXT, PDF, DOCX or pasted text). Questions written in the format above are read by a fixed parser (no AI), tagged by topic, and saved under that teacher's account only (never in the repo). In setup, pick sets and topic tags, for example just "Magnetism", to build a mission.

## Hosting

Run a single instance behind HTTPS. The included `render.yaml` proposes one paid Python service with a 1 GB persistent disk. The existing production service is at https://imposter.elanlavie.net/ (Render address: https://magnetic-mayhem.onrender.com/). GitHub source: https://github.com/elanlavie/magnetic-mayhem.

SQLite stores rooms, conversations, progress, and relay records. Only files on the mounted disk survive deployment. Rooms load for up to seven days; expired records remain in the database. This prototype has a 40-player room cap, not a classroom load guarantee. Use nicknames and manage retention appropriately. No student data leaves the server.

## Verification

Run `python3 -m unittest discover -s tests -v`.

The backend test suite covers hidden roles, private ballots, bot navigation, classroom and written meetings, tags, sabotage, ghost learning, restart recovery, scoring, retries, saved conversations, assigned names, relay validation and rewards, restart recovery, and multiplayer rules. Client checks cover onboarding, Enter / Shift+Enter / IME input, automatic countdowns, Escape, backdrop dismissal, and saved drafts. Chrome verification additionally exercises actual controls and rendering; the local UI fixture is separate from the production build. Real Sonnet integration is verified on the deployed service.
