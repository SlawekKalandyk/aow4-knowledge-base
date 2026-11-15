# Age of Wonders 4 knowledge base

Local, game-extracted AoW4 data as Markdown. Answer AoW4 questions from these files, not from memory or the web.
Data is current as of the commit in `SOURCE.md` (all DLCs up to then).

## Lookup order

1. Read the folder's `_index.md` table first. It answers most "which X has Y" questions (tier, affinity, cost, DLC, summary) in one read.
2. Open the item's file for full detail. File names are slugs: `Tome of Severing` → `tomes/tome-of-severing.md`. Glob `**/*severing*` if unsure.
3. Grep across the folders for an effect or keyword (e.g. `Vassal`, `Immobilized`, `Pillag`).
4. Large files (`glossary.md`, `status-effects.md`, `empire/structures.md`, `empire/item-forge.md`, `spells/_index.md`): grep them, don't read them whole.

## Layout

| Path | Contents |
|---|---|
| `tomes/` | 122 tomes; each file lists the units, spells, passives and upgrades it unlocks, linked. Tier 0 = culture/subculture tomes (`dark-cult-of-tyranny.md`), pacts and special research |
| `traits/society/`, `traits/form/`, `traits/destiny/` | Faction traits: point cost, affinity, effects, starting bonus, incompatibilities. Evil-act traits are marked. The Vision society traits list their Archon Prophecy visions |
| `units/` | Stats, cost, abilities with damage/range, passives, rank-up rewards, and the tome or culture that unlocks the unit |
| `spells/` | Type, cost, upkeep, unlocking tome, targets, full text |
| `cultures/` | One file per culture: description, starting affinity per subculture, culture/subculture tomes, units, buildings and society traits it can't take. The index table has every culture + subculture's starting affinity |
| `races.md` | The 24 race appearances with descriptions (cosmetic; gameplay comes from form traits) |
| `rulers.md` | Ruler origins (Champion, Wizard King, Eldritch Sovereign, …), dragon/giant/vampire subtypes |
| `world/` | Relics, free city factions (what absorbing one gives), ancient wonders/landmarks/magic materials, cosmic happenings |
| `heroes/` | Hero skill trees (one file per class, with the class description), ruler signature skills, hero items by slot, destinies |
| `empire/` | Empire skills, governors, city structures, siege projects, item forge |
| `glossary.md` | In-game concept tooltips (mechanics, terms) |
| `status-effects.md` | What each status effect does (Insanity, Bleeding, Stunned, …) |
| `builds/` | The user's own builds and notes. Hand-written; the only folder you should edit |

## Data quirks

- Some summary texts have blank numbers ("Base % chance", "for Turns"), mainly tome-unlocked units, passives and structures. If a number is blank, open the linked spell/unit file, which usually has it (unit files: ability damage, accuracy, range). Only if it's blank there too, say the value isn't in the data; never guess it.
- Affinity names: the data's `matter` = Materium and `arcana` = Astral (already translated in these files).
- DLC values are internal codes (`EMPIRESANDASHES`, `THRONESOFBLOOD`, `DRAGONLORDS`, …). `Base` = no DLC.
- `?` in a text = a value the game computes at runtime (e.g. "+?% bonus"); it isn't in the data, so don't guess it.
- Tome tier unlocking: every two tomes picked unlock the next tier (in-game tutorial). Affinity needed (player-provided, not in the game data): tier 3 = 3, tier 4 = 6, tier 5 = 8 points in the tome's affinity; tiers 1-2 need none. A dual-affinity tome counts both affinities combined, in any split (e.g. Tome of Dragons, Nature + Chaos: 2 Nature + 1 Chaos works). Shown as "Needs" in `tomes/_index.md` and in each tome file. To change it, edit `TIER_AFFINITY_NEEDED` in `build_kb.py`.
- Architect subcultures have starting affinity but no description in the data.
- Other limits: hero skills list "requires" ("any of" = one of them is enough, per the aow4db site's skill tree; Elementalist final skills are an exception), "Astral Dragon only" and the like (same-name Dragon Lord skills have one copy per dragon type) and "can't be taken with" (mutually exclusive skills); hero items list hero types and "disables slots"; item forge entries list "needs" (magic materials) and "fits" (item types; "lacks X" = item must not carry tag X); society traits list "Not available to cultures" and culture files "Can't take society traits"; destiny traits say how a race earns them. Rite cooldowns aren't in the data (its cooldown field just repeats the XP requirement). About 157 hero items have no effects in the data; most are item forge base types (Shield, Wedding Ring).
- Building limits in `empire/structures.md`: "Requires" = the game's requirement text; "Unlocked by" = the tome that unlocks it; "Built after" = its parent in the city building tree; "Boost requirements" = game field whose effect isn't in the data (don't guess it). "Culture building" lines, and the building lists in `cultures/`, come from the aow4db site's hand-made map (`../aow4db/HTML/CityTrees.html`), not game data: say so when you cite them. In that culture's cities, a standard building whose "Built after" parent the culture replaced follows the culture's version instead (Mercantile: Stone Walls follows Fortified Harbor, not Palisade Walls). Same-name versions of a structure, governor, spell, hero skill or item carry a label in their heading ("Giant King Governor (Frost Giant)", "Variant: Tunneling Spider", "Paragon Quarters (Warbound)"). The data has no field saying which version is which, so `build_kb.py` takes the label from the words where that version's own text differs from the others; it's a description, not a game name. "(variant 2 of 3)" = the versions differ in more than one short phrase; read their text to tell them apart.
- Units index "Source" blank = racial, summoned, wildlife or event unit.

## Maintenance

- Everything except `README.md`, `CLAUDE.md`, `builds/` and `build_kb.py` is generated; never edit it by hand. Fix `build_kb.py` instead.
- Refresh after a game patch: `git -C ../aow4db pull`, then `python build_kb.py`.
- `../aow4db/` is the raw source repo (about 1.6 GB, mostly images). Don't read its JSON unless a field is missing here; if so, extend `build_kb.py`.
