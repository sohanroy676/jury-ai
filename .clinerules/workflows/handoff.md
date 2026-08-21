# /handoff

Use this workflow at the end of a session to leave the project in a clean, resumable state.

Steps:

1. Update `memory-bank/progress.md` — move anything finished from "In progress" to "Done" with a brief note and date.
2. Update `memory-bank/activeContext.md` — current focus, recent decisions made this session, any open blockers/questions, and the single next step for the next session.
3. Update `memory-bank/systemPatterns.md` if any new conventions or patterns were established this session.
4. Update `ROADMAP.md` — move any completed features out of "Now"/"Next", and adjust priorities if this session changed the plan.
5. Run `/commit.md` in full (including its step 8) to commit all code changes and the regenerated CHANGELOG.md.
6. Confirm memory-bank files, ROADMAP.md, and CHANGELOG.md are all committed — do not leave documentation updates uncommitted alongside committed code.
7. Do not push without explicit approval.
