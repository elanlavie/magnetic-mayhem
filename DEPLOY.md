# Deployment proposal

Use a personal GitHub repository connected to a single Render Python web service.
The included render.yaml proposes paid compute and a 1 GB persistent disk.
Review Render's current cost before applying it. No resources have been purchased.

1. Publish this folder's contents at the root of a personal GitHub repository.
   Keep the repository private unless you want the source public.
2. In Render, create a Blueprint from that repository and inspect the proposed cost.
3. Enter ANTHROPIC_API_KEY in Render's secret environment settings, plus a private
   TEACHER_KEY of your choosing. Do not put either value in GitHub or browser code.
4. Deploy and check /api/config reports live and teacherProtected as true.
5. Open Mission control, enter the teacher code, enable the live tutor, create a
   small test room, and complete one real tutoring exchange. This incurs API usage.
6. Restart the service and confirm the test room and player progress remain.

The selected model is claude-sonnet-5-5. The server already sends requests to the
Claude Messages API with the appropriate Sonnet 5.5 thinking/effort settings.
Live API access still needs an authorized key and a real request to verify it.

Keep one server instance: rooms are held in memory and saved to SQLite on disk.
The deployment check is /api/config; the game itself is at the service root URL.
The app does not load .env files. Hosting environment settings provide the values.

This is a classroom pilot configuration. Live tutoring sends submitted curriculum
and student explanations to Anthropic. Use nicknames and review the original
README's hosting limits before student use.

Verification on November 8, 2026: all 22 backend tests passed; app.js passed Node's
syntax check. Live API access and hosted persistence have not yet been tested.
