# Age of Wonders 4 knowledge base

Local, game-extracted AoW4 data as Markdown. Answer AoW4 questions from these files, not from memory or the web.
Data is current as of the commit in `SOURCE.md` (all DLCs up to then).

## Lookup order

1. Read the folder's `_index.md` table first. It answers most "which X has Y" questions (tier, affinity, cost, DLC, summary) in one read.
2. Open the item's file for full detail. File names are slugs: `Tome of Severing` → `tomes/tome-of-severing.md`. Glob `**/*severing*` if unsure.
3. Grep across the folders for an effect or keyword (e.g. `Vassal`, `Immobilized`, `Pillag`).
4. Large files (`glossary.md`, `empire/structures.md`, `empire/item-forge.md`, `spells/_index.md`): grep them, don't read them whole.

## Layout

| Path | Contents |
|---|---|
| `tomes/` | 123 tomes; each file lists the units, spells, passives and upgrades it unlocks, linked. Tier 0 = culture/subculture tomes (`dark-cult-of-tyranny.md`), pacts and special research |
| `traits/society/`, `traits/form/`, `traits/destiny/` | Faction traits: point cost, affinity, effects, starting bonus, incompatibilities. Evil-act traits are marked |
| `units/` | Stats, cost, abilities with damage/range, passives, rank-up rewards, and the tome or culture that unlocks the unit |
| `spells/` | Type, cost, upkeep, unlocking tome, targets, full text |
| `cultures/` | One file per culture: description, starting affinity per subculture, culture/subculture tomes and units. The index table has every culture + subculture's starting affinity |
| `races.md` | The 24 race appearances with descriptions (cosmetic; gameplay comes from form traits) |
| `rulers.md` | Ruler origins (Champion, Wizard King, Eldritch Sovereign, …), dragon/giant/vampire subtypes, Archon Prophecy visions |
| `world/` | Relics, free city factions (what absorbing one gives), ancient wonders/landmarks/magic materials, cosmic happenings |
| `heroes/` | Hero skill trees, hero items by slot, destinies |
| `empire/` | Empire skills, governors, city structures, siege projects, item forge |
| `glossary.md` | In-game concept tooltips (status effects, mechanics) |
| `builds/` | The user's own builds and notes. Hand-written; the only folder you should edit |

## Data quirks

- Some summary texts have blank numbers ("Base % chance", "for Turns"), mainly tome-unlocked units, passives and structures. If a number is blank, open the linked spell/unit file, which usually has it (unit files: ability damage, accuracy, range). Only if it's blank there too, say the value isn't in the data; never guess it.
- Affinity names: the data's `matter` = Materium and `arcana` = Astral (already translated in these files).
- DLC values are internal codes (`EMPIRESANDASHES`, `THRONESOFBLOOD`, `DRAGONLORDS`, …). `Base` = no DLC.
- `?` in a text = a value the game computes at runtime (e.g. "+?% bonus"); it isn't in the data, so don't guess it.
- Tome tier unlocking: every two tomes picked unlock the next tier, and higher tiers also need some affinity (rule quoted in `tomes/_index.md`). The exact affinity amounts per tier are not in the data. Say so if a question needs them.
- Architect subcultures have starting affinity but no description in the data.
- Units index "Source" blank = racial, summoned, wildlife or event unit.

## Maintenance

- Everything except `README.md`, `CLAUDE.md`, `builds/` and `build_kb.py` is generated; never edit it by hand. Fix `build_kb.py` instead.
- Refresh after a game patch: `git -C ../aow4db pull`, then `python build_kb.py`.
- `../aow4db/` is the raw source repo (about 1.6 GB, mostly images). Don't read its JSON unless a field is missing here; if so, extend `build_kb.py`.
