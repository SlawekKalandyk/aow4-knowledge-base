# AoW4 Knowledge Base

Age of Wonders 4 game data as plain Markdown, for looking things up with Claude Code (or grep, or any editor) without searching the web.

It is generated from [aow4db](https://github.com/MinionsArt/aow4db), a community project that extracts the data from the game. It covers the base game and all DLCs up to the source commit in [`SOURCE.md`](SOURCE.md).

## Contents

| Folder | What's in it |
|---|---|
| [`tomes/`](tomes/_index.md) | 123 tomes: tier, affinity, DLC and everything each one unlocks (linked). Tier 0 holds culture/subculture tomes and pacts |
| [`traits/`](traits/) | Faction traits: 55 society, 79 form and 9 destiny traits, with cost, affinity, effects and starting bonus |
| [`units/`](units/_index.md) | 413 units: stats, cost, abilities, passives, rank-up rewards and where they come from |
| [`spells/`](spells/_index.md) | 579 spells: type, cost, upkeep, unlocking tome and full text |
| [`cultures/`](cultures/_index.md) | 12 cultures and 29 subcultures: description, starting affinity, culture tomes and units |
| [`races.md`](races.md) | The 24 race appearances |
| [`rulers.md`](rulers.md) | Ruler origins, dragon/giant/vampire subtypes, Archon Prophecy visions |
| [`world/`](world/_index.md) | Relics, free city factions, ancient wonders and landmarks, cosmic happenings |
| [`heroes/`](heroes/_index.md) | Hero skill trees, hero items by slot, destinies |
| [`empire/`](empire/_index.md) | Empire skills, governors, city structures, siege projects, item forge |
| [`glossary.md`](glossary.md) | In-game concept tooltips |
| [`builds/`](builds/) | My own faction builds and notes (hand-written) |

Every folder has an `_index.md` table to start from. Item files are named after the item, e.g. `tomes/tome-of-severing.md`.

## Using it with Claude Code

Start Claude Code in this folder. [`CLAUDE.md`](CLAUDE.md) is loaded automatically and tells Claude how to search the files and what the data doesn't cover.

## Updating after a game patch

The source data comes from a separate clone of aow4db, placed next to this repo:

```
AoW4-data/
  aow4db/                 git clone https://github.com/MinionsArt/aow4db.git
  aow4-knowledge-base/    this repo
```

```sh
git -C ../aow4db pull
python build_kb.py
git diff --stat           # shows what the patch changed
```

`build_kb.py` needs only Python 3 and rewrites every generated folder. It never touches `README.md`, `CLAUDE.md`, `builds/` or itself, so make fixes in the script, not in generated files.

## Not in the data

- The exact affinity amounts needed for each tome tier. The general rule (every two tomes unlock the next tier, and higher tiers also need affinity) is quoted in [`tomes/_index.md`](tomes/_index.md).
- Values the game computes at runtime, shown as `?` in the text.
- Descriptions for the Architect subcultures.

## Credits

All game data comes from [aow4db](https://github.com/MinionsArt/aow4db) by MinionsArt. Age of Wonders 4 is © Triumph Studios / Paradox Interactive. This is a private, unofficial reference.
