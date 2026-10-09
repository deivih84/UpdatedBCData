# BattleStats Update Summary AI Copy Rules

You may write friendly copy for a Battle Cats update summary, but factual data is already determined by the JSON diff.

Rules:

- Do not invent cat names, enemy names, stage names, IDs, counts, regions, or versions.
- Only mention facts present in the supplied `sections`.
- Keep wording concise and player-facing.
- Do not change `sections`, `sourceHashes`, `gameVersion`, `region`, `revision`, or `status`.
- Write only `copy.headline`, `copy.shortIntro`, and optional `section.summary` fields.
- If any source data looks incomplete or suspicious, add a short `reviewNotes` entry and keep `needsHumanReview` true.
- Any AI-authored copy must set `copy.source` to `ai_draft`.
- When generating EN and JP summaries from a shared data repository, pass the exact region version with `--game-version` instead of assuming `data_version.json` represents both regions.
