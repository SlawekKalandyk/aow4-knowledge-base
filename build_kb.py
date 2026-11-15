"""Generate a Claude-friendly Markdown knowledge base from the aow4db game data.

Usage:  python build_kb.py          (after `git pull` in ../aow4db)

Reads  ../aow4db/Data/EN/*.json  and rewrites every generated folder below.
Never touches CLAUDE.md, builds/ or this script.
"""
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

KB = Path(__file__).resolve().parent
SRC_REPO = KB.parent / "aow4db"
SRC = SRC_REPO / "Data" / "EN"
GEN = SRC_REPO / "Data" / "GEN"
GENERATED = ["tomes", "traits", "units", "spells", "cultures", "races.md", "rulers.md", "heroes", "empire", "world",
             "glossary.md", "status-effects.md", "SOURCE.md"]

# ---------------------------------------------------------------- markup cleanup

# Labels for icon tags like 12<gold></gold>. "" = drop (the text around it already says it).
ICON_LABELS = {
    "gold": "Gold", "mana": "Mana", "unitprod": "Draft", "structureprod": "Production",
    "influence": "Imperium", "knowledge": "Knowledge", "food": "Food",
    "souls": "Souls", "population": "Population", "thralls": "Thralls", "hp": "HP",
    "temphp": "Temporary HP", "defense": "Defense", "resistance": "Resistance",
    "statuseffectresistance": "Status Resistance", "crit": "Crit", "xp": "XP", "turn": "Turns",
    "production": "Production", "optactical": "Combat Casting Points",
    "caststrategic": "[World Map]", "casttactical": "[Combat]",
    "singleuseaction": "single-use action", "repeatingaction": "repeating action",
    "fullaction": "full action", "freeaction": "free action", "leaveoneaction": "leave-one action",
}
AFFINITY_TAGS = {"order": "Order", "chaos": "Chaos", "nature": "Nature", "arcana": "Astral",
                 "astral": "Astral", "matter": "Materium", "shadow": "Shadow"}


def icon_label(tag):
    t = tag.lower()
    if t in ICON_LABELS:
        return ICON_LABELS[t]
    if t.startswith("damage") and len(t) > 6:
        return t[6:].capitalize()
    if t.startswith("defense") and len(t) > 7:
        return t[7:].capitalize() + " Resistance"
    if t.startswith("empire") or t in AFFINITY_TAGS:
        return ""
    return ""  # unit classes, unit types, province icons: surrounding text names them


def ref_name(m):
    """{GLOBAL.UnitMoraleConcept.Hyperlink} -> glossary name; {GLOBAL.PROPERTIES.CONDEMNED.Hyperlink} -> Condemned."""
    concept = CONCEPT_NAMES.get(m.group(1))
    if concept:
        return concept
    last = re.sub(r"(Lore)?Concept$", "", m.group(2))
    if "_" in last or last.isupper():
        return last.replace("_", " ").title()
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", last)


CONCEPT_NAMES = {}  # filled after data load
NAMES_BY_KEY = {}  # "WARRIORSSOUL" -> "Warrior's Soul"; filled after data load

# Icon labels whose following word names them differently ("<hp></hp> Hit Points").
ICON_ALIASES = {"HP": "hit", "XP": "experience"}


_SPACED_CHAR = r"[A-Z0-9](?:_[0-9]?)*\.?"  # one letter, plus any '_' / '_2_' / '.' glued to it
SPACED_KEY = rf"{_SPACED_CHAR}(?: {_SPACED_CHAR}){{3,}}"  # 'P R O P E R T I E S. W A R R I O R S_ S O U L'


# Keys written without underscores, so they can't be split into words automatically.
SPACED_KEY_WORDS = {"HEAVYMELEESTRIKE": "Heavy Melee Strike", "CHANNELINGCHAMBER": "Channeling Chamber",
                    "BEACONOFUNITY": "Beacon of Unity", "COSMICFLUX_ELIXIR": "Cosmic Flux Elixir"}


def spaced_key_name(m):
    """Unresolved localization key spelled out letter by letter in raw text -> display name.
    'P R O P E R T I E S. W A R R I O R S_ S O U L' -> "Warrior's Soul"; unknown keys are title-cased."""
    raw = m.group(1).replace(" ", "")
    end = "." if raw.endswith(".") else ""  # the sentence's full stop, glued to the last letter
    *namespace, key = raw.rstrip(".").split(".")
    if namespace == ["MISC"]:
        return "?" + end  # MISC.* are runtime numbers (RACE_POPULATION_THRESHOLD)
    key = re.sub(r"^(HEROTRAIT_GOVERNANCE_|COMBATPROPERTY_)|_(UNIT_|TOOLTIP_)?(PROPERTY|ABILITY)$", "", key)
    key = re.sub(r"^GIANT_GOVERNOR_(\w+)$", r"\1_GIANT_GOVERNOR", key)  # GIANT_GOVERNOR_FIRE -> Fire Giant Governor
    name = SPACED_KEY_WORDS.get(key) or NAMES_BY_KEY.get(key.replace("_", ""))
    if not name:
        name = key.replace("_", " ").strip().title()
        name = re.sub(r"(?<= )(Of|The|To|And|In)\b", lambda w: w.group().lower(), name)
    return name + end


def clean(s):
    if not s:
        return ""
    s = str(s).replace('\\"', '"').replace("\\n", "\n")
    s = re.sub(rf"(?<=>)({SPACED_KEY})(?=</span>)", spaced_key_name, s)  # usually wrapped in <span>
    s = re.sub(rf"(?<![\w.])({SPACED_KEY}(?: {_SPACED_CHAR}){{4,}})(?![\w])", spaced_key_name, s)  # unwrapped, 8+ letters
    s = re.sub(r"<span[^>]*>|</span>", "", s)
    # Localization markup (all.json): [hyperlink,GLOBAL.X]Text[/hyperlink], [spellref,...]Text[/spellref]
    s = re.sub(r"\[(\w+),[^\]]*\](.*?)\[/\1\]", r"\2", s)
    # Named references like {GLOBAL.PROPERTIES.CONDEMNED.Hyperlink} -> "Condemned"
    s = re.sub(r"\{(GLOBAL\.[\w.]*?(\w+))\.Hyperlink\}", ref_name, s)
    # Unresolved runtime values such as {SUNDERED_RESISTANCE>ResolvedStrength} or {EventCity}
    s = re.sub(r"\{[^{}]*\}", "?", s)
    s = re.sub(r"\[/?\w+\]|\[\w+,[^\]]*\]", "", s)  # stray [/bulletlist], unclosed [spellref,...]
    s = re.sub(r"</?hyperlink>|</?helpcolor>|</?\w+Col(or)?>", "", s)
    s = re.sub(r"<br\s*/?>(</br>)?", "\n", s)
    s = s.replace("<bulletlist>", "\n").replace("</bulletlist>", "\n")
    s = s.replace("<bullet>", "\n- ").replace("</bullet>", "")

    def icon(m):
        num, tag, nxt = m.group(1), m.group(2), m.group(3).lower()
        label = icon_label(tag)
        # Bracketed labels are where something is cast ("[Combat] Combat Enchantment"), not a repeat: keep them,
        # except before that context's Casting Points ("[World Map] World Map Casting Points").
        if label.startswith("["):
            if nxt.startswith(label.strip("[]").lower() + " casting point"):
                label = ""
        elif nxt and (nxt.startswith(label.lower()[:4]) or nxt.startswith(ICON_ALIASES.get(label, "\0"))):
            label = ""  # following text already names it ("3 <turn></turn> Turns")
        if num:
            return f"{num} {label} "
        return f" {label} " if label else " "

    # Icon tags like 12<gold></gold>; peek (without consuming) at the following words to avoid "Food Food".
    s = re.sub(r"(?:([+-]?\d+%?)\s*)?<(\w+)></\2>(?=\s*([^<\n]{0,40}))", icon, s)
    s = re.sub(r" +([.,;:)])", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def flatten(text):
    """Join already-cleaned lines into one: list items with '; ', other lines as sentences ('. ' added when a line
    has no end punctuation); after ':' or an end mark just a space ("Razing a City: Takes -2 Turns. Gives 30 Gold")."""
    out = ""
    for line in text.split("\n"):
        line = line.strip()
        item = line.startswith("- ")
        line = line[2:].strip() if item else line
        if not line.strip(".,;: "):  # empty, or a stray full stop left after a closed list
            continue
        if not out:
            out = line
        elif re.search(r"[.!?:;]$", out):
            out += " " + line
        else:
            out += ("; " if item else ". ") + line
    return out


def join_items(items):
    """One-line list of already-flat entries, joined like flatten() joins list items."""
    return flatten("\n".join(f"- {x}" for x in items if x))


def one_line(s, n=None):
    s = flatten(clean(s)).replace("|", "/")
    return s if n is None or len(s) <= n else s[: n - 1].rstrip() + "…"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "unnamed"


def dlc(x):
    return (x.get("DLC") or "").strip() or "Base"


def tome_affinity(s):
    parts = re.findall(r"(\d+)\s*<empire(\w+)>", s or "")
    return ", ".join(f"{AFFINITY_TAGS.get(a, a.capitalize())} {n}" for n, a in parts)


def trait_affinity(lst):
    """'1<order></order> Order Affinity' -> 'Order 1'; '-10<reputation4></reputation4> Alignment' -> 'Alignment -10'.
    Affinities first, Alignment last."""
    out = []
    for a in lst or []:
        m = re.match(r"([+-]?\d+)\s*<(\w+)>", a.get("name", ""))
        if not m:
            out.append(clean(a.get("name")))
        elif m.group(2).startswith("reputation"):
            out.append(f"Alignment {m.group(1)}")
        else:
            out.append(f"{AFFINITY_TAGS.get(m.group(2), m.group(2))} {m.group(1)}")
    return ", ".join(sorted(out, key=lambda s: s.startswith("Alignment")))


def names(lst):
    out = []
    for d in lst or []:
        if isinstance(d, dict):
            v = d.get("name") or d.get("description") or d.get("requisite") or d.get("slug") or next(iter(d.values()), "")
            out.append(one_line(v))
        else:
            out.append(one_line(d))
    return [o for o in out if o]


def bullets(text):
    """Indent a cleaned multi-line text so it nests under a list item."""
    return clean(text).replace("\n", "\n  ")


_written = set()


def write(path, text):
    """Each generated file is written once; a second write means two records share a slug."""
    if path in _written:
        raise SystemExit(f"slug collision: {path} written twice")
    _written.add(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def load(name):
    return json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def unique(seq):
    """Drop repeats, keep first-seen order (identical rendered entries carry no extra information)."""
    return list(dict.fromkeys(seq))


def variant_labels(texts, max_words=4):
    """Label same-name versions of a record from their own text: the words between what all versions share at the
    start and at the end. The game data has no field saying which version is which, so "Fury of the Tunneling Spider"
    -> 'Tunneling Spider', "drafting of Frost Giant units" -> 'Frost Giant' (the span is extended over capitalized
    words after it). If the versions differ in more than one short span, all get 'variant n of m'."""
    toks = [re.findall(r"\S+|\n", t) for t in texts]
    pre = 0
    while all(len(t) > pre for t in toks) and len({t[pre] for t in toks}) == 1:
        pre += 1
    suf = 0
    while all(len(t) - suf > pre for t in toks) and len({t[-1 - suf] for t in toks}) == 1:
        suf += 1
    labels = []
    for t in toks:
        end = len(t) - suf
        span = t[pre:end]
        while span and span[-1] != "\n" and not re.search(r"[.,;:)]$", span[-1]) and end < len(t) and t[end][:1].isupper():
            span, end = span + [t[end]], end + 1
        words = [w for w in span if w != "\n"]
        if words and words[0].lower() in ("a", "an", "the"):
            words = words[1:]
        labels.append(" ".join(words).strip(".,;:()"))
    if all(labels) and len(set(labels)) == len(labels) and all(len(l.split()) <= max_words for l in labels):
        return labels
    return [f"variant {i} of {len(texts)}" for i in range(1, len(texts) + 1)]


def label_variants(entries):
    """entries: unique (name, meta, body) tuples. Same name and same meta line = versions a reader can't tell apart,
    so append a variant label to the name."""
    groups = defaultdict(list)
    for e in entries:
        groups[e[:2]].append(e)
    labels = {}
    for vs in groups.values():
        if len(vs) > 1:
            labels.update(zip(vs, variant_labels([body for _, _, body in vs])))
    return [(name + (f" ({labels[e]})" if e in labels else ""), meta, body) for e in entries for name, meta, body in [e]]


def dedupe(items):
    """Group records by id, dropping exact duplicates (ignoring resid)."""
    groups = defaultdict(list)
    for x in items:
        key = x.get("id") or slug(x.get("name"))
        body = {k: v for k, v in x.items() if k != "resid"}
        if body not in [{k: v for k, v in g.items() if k != "resid"} for g in groups[key]]:
            groups[key].append(x)
    return groups


# ---------------------------------------------------------------- data + lookups

tomes = [t for t in load("Tomes") if t.get("name") or t.get("id")]  # skip one empty record
for _t in tomes:  # tier 0 = culture/subculture tomes, pacts and other non-research tomes
    _t["tier"] = _t.get("tier") or 0
    _t["name"] = _t.get("name") or _t["id"].replace("_", " ").title()
# Skip empty placeholders and disabled traits (cut design leftovers like Doomed, plus Umbral Thralls and two mount
# form traits the player can't pick).
traits = [t for t in load("Traits") if (t.get("name") or t.get("id")) and t.get("enabled", True)]
units = [u for u in load("Units") if u.get("name") or u.get("id")]  # skip empty placeholder records
spells = load("Spells")
abilities = {a["slug"].lower(): a for a in load("Abilities")}
# Deprecated unit records carry a "DEPRECATED UNIT!" passive: 9 retired units, and 3 stale Magma Spirit copies that
# would otherwise shadow the live one.
units = [u for u in units if not any("DEPRECATED" in (abilities.get(p["slug"].lower(), {}).get("name") or "")
                                     for p in u.get("primary_passives", []) + u.get("secondary_passives", []))]
hero_skills = load("HeroSkills")
hero_items = load("HeroItems")
structures = load("StructureUpgrades")
siege = load("SiegeProjects")
progression = load("EmpireProgression")
governance = load("Governance")
destinies = load("Destinies")
forge_types = load("ItemForgeTypes")
forge_upgrades = load("ItemForgeUpgrades")
concepts = load("concept_tooltips")
CONCEPT_NAMES.update({k: v["name"] for k, v in concepts.items() if v.get("name")})


def _collect_names(x):
    if isinstance(x, dict):
        n = x.get("name")
        if isinstance(n, str) and n and "<" not in n:
            NAMES_BY_KEY.setdefault(re.sub(r"[^A-Z0-9]", "", n.upper()), n)
        for v in x.values():
            _collect_names(v)
    elif isinstance(x, list):
        for v in x:
            _collect_names(v)


_collect_names([load("StatusEffects"), list(concepts.values()), units, list(abilities.values()), hero_skills,
                hero_items, structures, spells, tomes])
# Full English localization keyed by id; GEN/*.json records point into it via extraLookup/lookup.
loc = {x["id"]: x for x in load("all")}


def load_gen(name):
    return json.loads((GEN / f"{name}.json").read_text(encoding="utf-8"))


faction = load_gen("FactionCreation")
relics = load_gen("Relics")
free_cities = load_gen("FreeCities")
world_structures = load_gen("WorldStructures")
cosmic = load_gen("CosmicHappenings")

unit_groups = dedupe(units)
spell_groups = dedupe(spells)
STRUCTURE_CATEGORIES = {"conduit": "Conduit", "mine": "Mine", "researchpost": "Research Post", "quarry": "Quarry",
                        "forester": "Forester", "farm": "Farm", "farms": "Farm", "teleporter": "Teleporter",
                        "magicvictory": "Magic Victory", "expansionvictory": "Expansion Victory"}


def split_icon_name(name):
    """'<conduit></conduit> Accursed Grave' -> ('Conduit', 'Accursed Grave'). Some structure names start with the
    icon of the improvement or victory type they count as; it isn't part of the name."""
    m = re.match(r"\s*<(\w+)></\1>\s*(.*)", name or "", re.S)
    if not m:
        return "", name
    return STRUCTURE_CATEGORIES.get(m.group(1).lower(), m.group(1).capitalize()), m.group(2)


for _s in structures:
    _s["category"], _s["name"] = split_icon_name(_s["name"])
for _t in tomes:
    for _sk in _t.get("skills", []):
        _sk["name"] = split_icon_name(_sk["name"])[1]
structure_by_id = {s["id"]: s for s in structures}
hero_skill_by_id = {h["id"]: h for h in hero_skills}

unit_tome, spell_tome = defaultdict(list), defaultdict(list)
for t in tomes:
    for sk in t.get("skills", []):
        if sk.get("unit_slug"):
            unit_tome[sk["unit_slug"]].append(t["name"])
        if sk.get("spell_slug"):
            spell_tome[sk["spell_slug"]].append(t["name"])

# Tomes that unlock a structure: "City Structure" tome skills plus the tome's initial city upgrades.
structure_tomes = defaultdict(list)
for t in tomes:
    ups = [sk.get("upgrade_slug") for sk in t.get("skills", [])] + [u.get("upgrade_slug") for u in t.get("initial_upgrades", [])]
    for sid in filter(None, ups):
        if t not in structure_tomes[sid]:
            structure_tomes[sid].append(t)

CITY_TIERS = ["II", "III", "IV"]


def city_tree_prereqs():
    """GEN/CityTree.json: each node lists the nodes it hangs off in the city building tree.
    town_hall_ii..iv are city tiers; town_hall_i_town_center is the root. '*x' stands for the six affinity
    versions of x. Parents missing from StructureUpgrades (an older Wizard Tower layout) are dropped."""
    tiers, after = defaultdict(set), defaultdict(set)
    affinities = sorted({a.lower() for a in AFFINITY_TAGS.values()})
    for node in load_gen("CityTree"):
        nid = node["id"]
        ids = [f"{a}_{nid[1:]}" for a in affinities] if nid.startswith("*") else [nid]
        for p in (c["id"] for c in node["connectTo"]):
            tier = re.fullmatch(r"town_hall_(ii|iii|iv)", p)
            for i in ids:
                if tier:
                    tiers[i].add(tier.group(1).upper())
                elif p in structure_by_id:
                    after[i].add(p)
    return tiers, after


def faction_full_name(f):
    """'Cult of Death' (subculture of Dark) -> 'Dark - Cult of Death'; cultures and prefixed subcultures unchanged."""
    if f["type"] == "SubCulture" and " - " not in f["name"]:
        return f"{f['requirement']} - {f['name']}"
    return f["name"]


def culture_buildings():
    """Culture/subculture building swaps from the aow4db site's hand-made map (HTML/CityTrees.html,
    `overrideBuildings`), not game data. Returns {structure id: [(faction full name, culture, what it does, base id)]}
    and {faction full name: {base id: replacement id}}."""
    page = SRC_REPO / "HTML" / "CityTrees.html"
    m = page.exists() and re.search(r"const overrideBuildings = \{(.*?)\n\s*\};", page.read_text(encoding="utf-8"), re.S)
    if not m:
        print("WARNING: overrideBuildings not found in aow4db/HTML/CityTrees.html; culture buildings skipped")
        return {}, {}
    keys = {slug(faction_full_name(f)).replace("-", "_"): (faction_full_name(f), f.get("requirement") or f["name"])
            for f in faction if f["type"] in ("Culture", "SubCulture")}
    out, swaps = defaultdict(list), defaultdict(dict)
    for key, entries in re.findall(r"(\w+): \[(.*?)\]", re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S), re.S):
        hits = [k for k in keys if k == key] or [k for k in keys if k.startswith(key)]  # site: reaver_federate
        if len(hits) != 1:
            print(f"WARNING: culture map key {key!r} matches no single culture/subculture; skipped")
            continue
        full, culture = keys[hits[0]]
        for base, new in re.findall(r'"([\w-]+):([\w-]+)"', entries):
            if new not in structure_by_id:
                print(f"WARNING: culture map building {new!r} ({key}) not in StructureUpgrades; skipped")
                continue
            if base in structure_by_id:
                what = f"replaces {clean(structure_by_id[base]['name'])}"
            elif re.fullmatch(r"town_hall_(ii|iii|iv)", base):
                what = f"replaces Town Hall {base.rsplit('_', 1)[1].upper()}"
            elif base == "extraBase":
                what = "extra building"
            else:  # iii_unlock* slots
                what = "unique building"
            out[new].append((full, culture, what, base))
            swaps[full][base] = new
    return out, swaps


def culture_built_after(full, culture, base):
    """A culture building that replaces `base` sits in base's place in the city tree; base's parents are
    themselves swapped if the same culture/subculture (or its parent culture) replaces them."""
    if base not in structure_by_id:
        return ""
    swap = {**culture_swaps.get(culture, {}), **culture_swaps.get(full, {})}
    parents = " or ".join(sorted(clean(structure_by_id[swap.get(p, p)]["name"]) for p in city_after.get(base, ())))
    tiers = [f"City Tier {t}" for t in sorted(city_tiers.get(base, ()), key=CITY_TIERS.index)]
    return " and ".join(b for b in [parents, *tiers] if b)


city_tiers, city_after = city_tree_prereqs()
culture_building_of, culture_swaps = culture_buildings()
CULTURE_MAP_NOTE = "aow4db site's hand-made culture map, not game data"

hero_skill_by_resid = {h["resid"]: h for h in hero_skills}
tome_by_name = {t["name"]: t for t in tomes}
# Ascension hero skill id -> names of the tomes that grant it ("Tome of Beasts, Tome of Vigor").
ascended_tomes = {a["id"]: [n.strip() for n in a["description"].split(",")] for a in load_gen("AscendedInfo")}
# Ruler origins (by id) and form traits (by name) that come with spells.
origin_spells = {o["id"]: o for o in load_gen("ExtraLookSpellsOrigin")}
# The data spells the form traits "Arctic Adaption"; the traits are named "Arctic Adaptation".
origin_spells.update({o["name"].replace("Adaption", "Adaptation"): o for o in origin_spells.copy().values()})
destiny_triggers = {d["id"]: d for d in load_gen("DestinyTraits")}  # how a race earns a destiny trait
world_combat_enchantments = defaultdict(list)  # world structure id -> combat enchantments it gives
for _c in load_gen("CombatEnchantments"):
    world_combat_enchantments[_c["origin_structure"]].append(_c)
culture_incompatible = defaultdict(list)  # cleaned society trait name -> cultures/subcultures that can't take it
for _f in faction:
    for _i in _f.get("incompatible") or []:
        culture_incompatible[clean(_i["name"])].append(faction_full_name(_f))
siege_tomes = defaultdict(list)
for t in tomes:
    for sk in t.get("skills", []):
        if sk.get("siege_project_slug"):
            siege_tomes[sk["siege_project_slug"]].append(t)


def tome_ref(t, frm="../"):
    return f"[{t['name']}]({frm}tomes/{slug(t['id'])}.md) (tier {t['tier']})"


def tag_name(tag):
    """'ItemTypeWeapon.TwoHandedHeavy.Greatsword' -> 'Greatsword'; 'HeroSkillArchetype.PhysicalRanged' ->
    'Physical Ranged hero archetype'."""
    parts = tag.strip().split(".")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", parts[-1])
    return f"{name} hero archetype" if parts[0] == "HeroSkillArchetype" else name


def tag_filter(node):
    """Item forge tag filter -> 'any of (Greatsword, Greataxe)'; 'lacks X' = the item must not carry tag X."""
    cond = node.get("condition", "")
    kids = [tag_filter(c) for c in node.get("children", [])]
    m = re.match(r"(Contains|Does not contain)(?: inherited)? (\S+)", cond)
    if m:
        return ("lacks " if m.group(1) != "Contains" else "") + tag_name(m.group(2))
    if not kids:
        return one_line(cond)
    if len(kids) == 1:
        return kids[0]
    return f"{'all' if cond.startswith('All') else 'any'} of ({', '.join(kids)})"


def token_needs(reqs):
    """[{'num_required': 2, 'token_name': 'Archon Blood'}] -> '2 Archon Blood' (duplicates in the data dropped)."""
    out = []
    for r in reqs or []:
        s = f"{r.get('num_required')} {r.get('token_name')}"
        if s not in out:
            out.append(s)
    return ", ".join(out)


def unit_link(uid, frm):
    if uid in unit_groups:
        return f"[{unit_groups[uid][0]['name']}]({frm}units/{slug(uid)}.md)"
    return uid


def spell_link(sid, frm):
    if sid in spell_groups:
        return f"[{spell_groups[sid][0]['name']}]({frm}spells/{slug(sid)}.md)"
    return sid


def ability_line(slug_):
    a = abilities.get(slug_.lower())
    if not a:
        return None
    stats = [p for p in [
        one_line(a.get("damage")) and f"damage {one_line(a.get('damage'))}",
        a.get("accuracy") and f"accuracy {a['accuracy']}",
        a.get("range") and f"range {a['range']}",
        one_line(a.get("actionPoints")),
    ] if p]
    head = f"**{clean(a['name'])}**" + (f" ({', '.join(stats)})" if stats else "")
    body = [clean(a.get("description"))]
    body += [f"{clean(m.get('name'))}: {one_line(m.get('description'))}" for m in a.get("modifiers", []) if m.get("description")]
    body += [one_line(n.get("note")) for n in a.get("notes", [])]
    req = names(a.get("requisites"))
    if req:
        body.append("Requires: " + ", ".join(req))
    text = flatten("\n".join(one_line(b) for b in body if b))  # parts as sentences: "1 Turns. Requires: Melee"
    return f"- {head}: {text}" if text else f"- {head}"


# ---------------------------------------------------------------- tomes

# Player-provided (not in the game data): affinity a tome's own affinities must reach to unlock it.
# A dual-affinity tome counts both of its affinities combined, in any split.
TIER_AFFINITY_NEEDED = {3: 3, 4: 6, 5: 8}
TIER_RULE_NOTE = ("Affinity needed (player-provided, not in the game data): tier 3 = 3, tier 4 = 6, tier 5 = 8 points "
                  "in the tome's affinity; a dual-affinity tome counts both affinities combined, in any split. "
                  "Tiers 1-2 need no affinity.")


def affinity_needed(t):
    if not t["tier"]:
        return ""
    need = TIER_AFFINITY_NEEDED.get(t["tier"])
    if not need:
        return "none"
    kinds = re.findall(r"([A-Za-z]+) \d", tome_affinity(t.get("affinities")))
    return f"{need} {kinds[0]}" if len(kinds) == 1 else f"{need} combined {' + '.join(kinds)}"


def build_tomes():
    rows = []
    for t in sorted(tomes, key=lambda t: (t["tier"], tome_affinity(t.get("affinities")), t["name"])):
        aff = tome_affinity(t.get("affinities"))
        need = affinity_needed(t)
        rows.append([f"[{t['name']}]({slug(t['id'])}.md)", t["tier"], aff, need, dlc(t), one_line(t.get("gameplay_description"))])
        lines = [f"# {t['name']}", "",
                 f"- Tier: {t['tier']}", f"- Affinity granted: {aff}"]
        if need:
            lines.append(f"- Affinity needed to unlock: {need} (player-provided rule, not in the game data)")
        lines += [f"- DLC: {dlc(t)}", "",
                 one_line(t.get("gameplay_description")), "", "## Unlocks", ""]
        for sk in t.get("skills", []):
            kind = one_line(sk.get("type"))
            name = clean(sk["name"])
            # Tome skill text is a template with numbers blanked; the spell record has the real values.
            desc = sk.get("description")
            if sk.get("unit_slug"):
                name = unit_link(sk["unit_slug"], "../")
            elif sk.get("spell_slug"):
                name = spell_link(sk["spell_slug"], "../")
                spell = spell_groups.get(sk["spell_slug"])
                if spell and spell[0].get("description"):
                    desc = spell[0]["description"]
            lines.append(f"- {name} ({kind}): {bullets(desc)}")
        for p in t.get("passives", []):
            lines.append(f"- {clean(p['name'])} ({one_line(p.get('type'))}): {bullets(p.get('description'))}")
        for u in t.get("initial_upgrades", []):
            s = structure_by_id.get(u.get("upgrade_slug"))
            if s:
                lines.append(f"- {clean(s['name'])} (Initial City Upgrade): {one_line(s.get('description') or s.get('prediction_description'))}")
        hs = [hero_skill_by_id.get(h.get("slug")) for h in t.get("hero_skills", [])]
        for h in filter(None, hs):
            lines.append(f"- {clean(h['name'])} (Hero Skill): {one_line(h.get('description'))}")
        write(KB / "tomes" / f"{slug(t['id'])}.md", "\n".join(lines))
    headers = ["Tome", "Tier", "Affinity", "Needs", "DLC", "Summary"]
    rule = one_line(loc.get("TUTORIAL@TOMESELECTION@PAGE02", {}).get("description"))
    write(KB / "tomes" / "_index.md", "# Tomes\n\n"
          f"Affinity = affinity points the tome grants. Unlock rule (in-game tutorial): {rule}\n\n"
          f"Needs = {TIER_RULE_NOTE}\n\n"
          "## Magic tomes (researchable, tiers 1-5)\n\n" + table(headers, [r for r in rows if r[1]])
          + "\n\n## Tier 0: culture/subculture tomes, pacts and other non-research tomes\n\n"
          "Culture tomes (named 'Culture - Subculture') hold what that culture/subculture unlocks.\n\n"
          + table(headers, [r for r in rows if not r[1]]))


# ---------------------------------------------------------------- traits

def vision_line(s):
    """An Archon Prophecy vision: a sub-option of a Vision society trait (its `requirement`)."""
    aff = fmt_affinity(affinity_tags(s.get("affinity")))
    objective = loc.get(s.get("objective", ""), {}).get("objective_1", "")
    rewards = [one_line(v) for r in s.get("rewards", []) for k, v in loc.get(r, {}).items() if k not in ("id", "DLC")]
    return (f"- **{clean(s['name'])}** ({aff + ', ' if aff else ''}DLC {dlc(s)}): "
            + join_items([f"objective: {one_line(objective) or '?'}", rewards and f"rewards: {flatten(chr(10).join(rewards))}"]))


def build_traits():
    by_type = defaultdict(list)
    for t in traits:
        by_type[t.get("type") or "other"].append(t)
    for typ, items in by_type.items():
        rows = []
        for t in sorted(items, key=lambda t: (t.get("group_name") or "", t.get("display_order", 0), t["name"])):
            name = clean(t["name"])
            evil = " (evil act)" if "evilact" in t["name"] else ""
            fname = slug(t.get("id") or name) + ".md"
            effects = names(t.get("effect_descriptions"))
            aff = trait_affinity(t.get("affinities"))
            rows.append([f"[{name}]({fname}){evil}", t.get("point_cost", ""), t.get("group_name", ""), aff, dlc(t),
                         join_items(effects)])
            lines = [f"# {name}{evil}", "", f"- Type: {typ} trait", f"- Point cost: {t.get('point_cost', '')}"]
            if t.get("group_name"):
                lines.append(f"- Group: {t['group_name']}")
            if aff:
                lines.append(f"- Affinity: {aff}")
            lines.append(f"- DLC: {dlc(t)}")
            inc = names(t.get("incompatible_society_traits"))
            if inc:
                lines.append(f"- Incompatible with: {', '.join(inc)}")
            if culture_incompatible.get(name):
                lines.append(f"- Not available to cultures: {', '.join(culture_incompatible[name])}")
            trig = destiny_triggers.get(t.get("id"))
            if trig:
                lines.append("- Earned when: " + join_items(one_line(e.get("entry")) for e in trig.get("trigger", [])))
            granted = origin_spells.get(name) or origin_spells.get(t.get("id"))
            if granted:
                lines.append("- Grants spells: " + ", ".join(spell_link(s["id"], "../../") for s in granted.get("spell", [])))
            lines += ["", "## Effects", ""] + [f"- {e}" for e in effects]
            sb = names(t.get("starting_bonuses"))
            if sb:
                lines += ["", "## Starting bonus", ""] + [f"- {b}" for b in sb]
            visions = [vision_line(s) for s in faction if s["type"] == "SubSociety" and s.get("requirement") == name]
            if visions:
                lines += ["", "## Visions (Archon Prophecy)", ""] + visions
            desc = [clean(t.get(k)) for k in ("screen_description", "lore_description", "biography_description")]
            desc = [d for i, d in enumerate(desc) if d and d not in desc[:i]]
            if desc:
                lines += ["", "## Description", ""] + desc
            write(KB / "traits" / typ / fname, "\n".join(lines))
        write(KB / "traits" / typ / "_index.md", f"# {typ.capitalize()} traits\n\n"
              + table(["Trait", "Cost", "Group", "Affinity", "DLC", "Effects"], rows))


# ---------------------------------------------------------------- units + cultures

def build_units():
    rows = []
    cultures = defaultdict(lambda: defaultdict(list))
    for uid, variants in sorted(unit_groups.items(), key=lambda kv: (kv[1][0]["tier"], kv[1][0]["name"])):
        u = variants[0]
        cult = sorted({(v.get("culture_name"), v.get("sub_culture_name")) for v in variants if v.get("culture_name")})
        for c, sc in cult:
            cultures[c][sc or "(all subcultures)"].append(uid)
        source = [f"Tome: {t}" for t in unit_tome.get(uid, [])]
        source += [f"Culture: {c}" + (f" / {sc}" if sc else "") for c, sc in cult]
        rows.append([f"[{u['name']}]({slug(uid)}.md)", u["tier"], u["hp"], u["armor"], u["resistance"],
                     one_line(u.get("cost")), "; ".join(source), dlc(u)])
        lines = [f"# {u['name']}", "",
                 f"- Tier: {u['tier']}",
                 f"- HP {u['hp']} | Defense {u['armor']} | Resistance {u['resistance']} | Status resistance {u.get('status_resistance', 0)}",
                 f"- Movement {u['mp']} | Combat speed {u.get('combat_speed', '')}",
                 f"- Cost: {one_line(u.get('cost'))} | Upkeep: {one_line(u.get('upkeep'))}",
                 f"- DLC: {dlc(u)}"]
        if source:
            lines.append(f"- Source: {'; '.join(source)}")
        res = [r["slug"].replace("_", " ") for r in u.get("resistances", [])]
        if res:
            lines.append(f"- Damage resistances: {', '.join(res)}")
        if u.get("evolve_target"):
            lines.append(f"- Evolves into: {unit_link(u['evolve_target'], '../')}")
        if clean(u.get("description")):
            lines += ["", clean(u["description"])]
        for title, key in [("Abilities", "abilities"), ("Passives", "primary_passives"), ("Unit type traits", "secondary_passives")]:
            ab = unique(a for a in (ability_line(a["slug"]) for a in u.get(key, [])) if a)  # raw lists repeat some
            if ab:
                lines += ["", f"## {title}", ""] + ab
        medals = []
        for r in range(2, 7):
            got = [clean(abilities[a["slug"].lower()]["name"]) for a in u.get(f"medal_rewards_{r}", []) if a["slug"].lower() in abilities]
            if got:
                medals.append(f"- Rank {r}: {', '.join(got)}")
        if medals:
            lines += ["", "## Rank-up rewards", ""] + medals
        write(KB / "units" / f"{slug(uid)}.md", "\n".join(lines))
    write(KB / "units" / "_index.md", "# Units\n\nSource lists the tomes and cultures that unlock a unit; blank = racial, summoned, wildlife or event units.\n\n"
          + table(["Unit", "Tier", "HP", "Def", "Res", "Cost", "Source", "DLC"], rows))
    return cultures


# ---------------------------------------------------------------- cultures, races, rulers

def affinity_tags(s):
    """'<empireshadow></empireshadow>, <empireshadow></empireshadow>' -> {'Shadow': 2}"""
    out = defaultdict(int)
    for a in re.findall(r"<empire(\w+)>", s or ""):
        out[AFFINITY_TAGS.get(a, a.capitalize())] += 1
    return out


def fmt_affinity(d):
    return ", ".join(f"{k} {v}" for k, v in d.items())


def loc_text(key, *fields):
    rec = loc.get(key or "", {})
    return [clean(rec[f]) for f in fields if rec.get(f)]


def build_cultures(culture_units):
    cultures = [x for x in faction if x["type"] == "Culture"]
    subs = [x for x in faction if x["type"] == "SubCulture"]
    culture_tomes = [t for t in tomes if not t["tier"]]
    buildings = defaultdict(list)  # faction full name -> "Black Market (replaces Market)"
    for sid, uses in culture_building_of.items():
        for full, _, what, _ in uses:
            buildings[full].append(f"{clean(structure_by_id[sid]['name'])} ({what})")
    building_note = f" ({CULTURE_MAP_NOTE}; details in [structures](../empire/structures.md))"
    rows = []
    for c in cultures:
        cname = c["name"]
        fname = f"{slug(cname)}.md"
        c_aff = affinity_tags(c.get("affinity"))
        lines = [f"# {cname} culture", "", f"- Culture affinity: {fmt_affinity(c_aff) or 'none (comes from subculture)'}",
                 f"- DLC: {dlc(c)}", ""]
        lines.append("\n\n".join(loc_text(c.get("extraLookup"), "bio", "description", "fpg_description", "lore")))
        tome = [t for t in culture_tomes if t["name"] == cname]
        if tome:
            lines += ["", f"Culture tome: [{tome[0]['name']}](../tomes/{slug(tome[0]['id'])}.md)"]
        units_all = culture_units.get(cname, {})
        if units_all.get("(all subcultures)"):
            lines += ["", "Culture units: " + ", ".join(unit_link(u, "../") for u in units_all["(all subcultures)"])]
        if buildings[cname]:
            lines += ["", f"Culture buildings{building_note}: " + ", ".join(sorted(buildings[cname]))]
        if c.get("incompatible"):
            lines += ["", "Can't take society traits: " + ", ".join(clean(i["name"]) for i in c["incompatible"])]
        my_subs = [s for s in subs if s.get("requirement") == cname]
        if not my_subs:
            rows.append([f"[{cname}]({fname})", "-", fmt_affinity(c_aff), dlc(c)])
        for s in my_subs:
            short = s["name"].split(" - ", 1)[-1]
            total = defaultdict(int, c_aff)
            for k, v in affinity_tags(s.get("affinity")).items():
                total[k] += v
            rows.append([f"[{cname}]({fname})", short, fmt_affinity(total), dlc(s)])
            lines += ["", f"## Subculture: {short}", "",
                      f"- Starting affinity (culture + subculture): {fmt_affinity(total)}", f"- DLC: {dlc(s)}"]
            tome = [t for t in culture_tomes if t["name"].startswith(cname) and short.lower() in t["name"].lower()]
            if tome:
                lines.append(f"- Subculture tome: [{tome[0]['name']}](../tomes/{slug(tome[0]['id'])}.md)")
            sub_units = [u for sc, us in units_all.items() if sc != "(all subcultures)"
                         and (sc.lower() in short.lower() or short.lower() in sc.lower()) for u in us]
            if sub_units:
                lines.append("- Units: " + ", ".join(unit_link(u, "../") for u in sub_units))
            if buildings[faction_full_name(s)]:
                lines.append(f"- Buildings{building_note}: " + ", ".join(sorted(buildings[faction_full_name(s)])))
            if s.get("incompatible"):
                lines.append("- Can't take society traits: " + ", ".join(clean(i["name"]) for i in s["incompatible"]))
            desc = loc_text(s.get("extraLookup"), "description") or [clean(s.get("description"))]
            lines += ["", *[d for d in desc if d]] if any(desc) else []
        write(KB / "cultures" / fname, "\n".join(lines))
    other = [t for t in culture_tomes if not any(t["name"].startswith(c["name"]) for c in cultures)]
    write(KB / "cultures" / "_index.md", "# Cultures and subcultures\n\n"
          "Starting affinity = culture affinity + subculture affinity. Each culture file has the description, "
          "culture/subculture tomes (what they unlock) and culture units.\n\n"
          + table(["Culture", "Subculture", "Starting affinity", "DLC"], rows)
          + "\n\n## Other tier-0 tomes (pacts, special research)\n\n"
          + "\n".join(f"- [{t['name']}](../tomes/{slug(t['id'])}.md)" for t in sorted(other, key=lambda t: t["name"])))


def build_races():
    skins = [x for x in faction if x["type"] == "Skin"]
    lines = ["# Races (appearances)", "",
             "In AoW4 a race is an appearance plus form traits. Appearances are cosmetic; the gameplay comes from "
             "form traits (see [traits/form](traits/form/_index.md)).", ""]
    lines += [f"- **{s['name']}** ({dlc(s)}): {' '.join(loc_text(s.get('extraLookup'), 'bio'))}" for s in skins]
    write(KB / "races.md", "\n".join(lines))


def build_rulers():
    lines = ["# Rulers", "", "## Ruler origins", ""]
    for r in (x for x in faction if x["type"] == "Ruler Origin"):
        lines += [f"### {r['name']}", "", f"DLC: {dlc(r)}", ""]
        if origin_spells.get(r.get("id")):
            lines += ["Origin spells: " + ", ".join(spell_link(s["id"], "") for s in origin_spells[r["id"]]["spell"]), ""]
        lines += ["\n\n".join(loc_text(r.get("extraLookup"), "description_short", "description")), ""]
    lines += ["## Ruler subtypes", ""]
    for s in (x for x in faction if x["type"] == "SubType"):
        aff = fmt_affinity(affinity_tags(s.get("affinity")))
        lines.append(f"- **{s['name']}** ({s.get('requirement', '')}{', ' + aff if aff else ''}, DLC {dlc(s)}): "
                     + one_line(" ".join(loc_text(s.get("extraLookup"), "description"))))
    write(KB / "rulers.md", "\n".join(lines))


# ---------------------------------------------------------------- world: relics, free cities, wonders, happenings

def slug_list(val):
    return [v.strip() for v in str(val).split(",") if v.strip()]


def combat_enchantment_line(c):
    desc = one_line(" ".join(loc_text(c.get("extraLookup"), "description")) or c.get("description"))
    return f"- Combat enchantment: {clean(c['name'])}" + (f": {desc}" if desc else " (no description in data)")


def build_world():
    lines = ["# Relics", ""]
    for r in sorted(relics, key=lambda r: r["name"]):
        sp = [spell_link(s["id"], "../") for s in r.get("spell", [])]
        un = [unit_link(x["id"], "../") for x in r.get("unit_unlock", []) if isinstance(x, dict) and x.get("id")]
        lines += [f"## {r['name']}", "", f"DLC: {dlc(r)}" + (f" | Spells: {', '.join(sp)}" if sp else "")
                  + (f" | Units: {', '.join(un)}" if un else ""), ""]
        lines += loc_text(r.get("extraLookup"), "description") + loc_text(r.get("unlock"), "name", "description") + [""]
    write(KB / "world" / "relics.md", "\n".join(lines))

    lines = ["# Free city factions (minor factions)", "",
             "What a free city of this faction offers when you absorb/vassalize it.", ""]
    for f in sorted(free_cities, key=lambda f: loc.get(f["lookup"], {}).get("name", f["id"])):
        rec = loc.get(f["lookup"], {})
        lines += [f"## {clean(rec.get('name')) or f['id']}", "", f"DLC: {dlc(f)}", "", clean(rec.get("description")), ""]
        for label, key in [("Always", "mandatory"), ("Possible upgrades", "upgrades")]:
            for entry in f.get(key, []):
                for kind, val in entry.items():
                    if kind == "units":
                        items = [unit_link(u, "../") for u in slug_list(val)]
                    elif kind == "spells":
                        items = [spell_link(s, "../") for s in slug_list(val)]
                    else:
                        items = [v.replace("_", " ") for v in slug_list(val)]
                    lines.append(f"- {label} – {kind}: {', '.join(items)}")
        lines.append("")
    write(KB / "world" / "free-cities.md", "\n".join(lines))

    lines = ["# World structures (ancient wonders, landmarks, magic materials, spawners)", ""]
    for w in sorted(world_structures, key=lambda w: (one_line(w.get("type")), w["name"])):
        meta = [one_line(w.get("type")), f"DLC {dlc(w) if (w.get('DLC') or w.get('dlc')) else 'Base'}"]
        if w.get("nodeType"):
            meta.append("node: " + one_line(w["nodeType"].replace("&", " ")))
        lines += [f"## {clean(w['name'])}", "", f"({'; '.join(m for m in meta if m)})", ""]
        lines += loc_text(w.get("extraLookup"), "description")
        un = [unit_link(u["slug"], "../") for u in w.get("unit_unlocks", []) if isinstance(u, dict)]
        if un:
            lines.append(f"- Unit unlocks: {', '.join(un)}")
        sp = []
        for key in ("spell_unlocks", "spell_rewards"):
            val = w.get(key)
            if isinstance(val, list):
                sp += [spell_link(s["id"], "../") for s in val if isinstance(s, dict) and s.get("id")]
            elif isinstance(val, str):  # a combat property, described in the localization
                rec = loc.get(val, {})
                sp.append(f"{clean(rec.get('name')) or val}: {one_line(rec.get('description'))}")
        if sp:
            lines.append(f"- Spell unlocks/rewards: {'; '.join(sp)}")
        lines += [combat_enchantment_line(c) for c in world_combat_enchantments.get(w.get("id"), [])]
        lines.append("")
    unmatched = [(src, c) for src, cs in world_combat_enchantments.items() if src not in {w.get("id") for w in world_structures}
                 for c in cs]
    if unmatched:
        lines += ["## Other combat enchantments", "", "Their source isn't a listed world structure.", ""]
        lines += [combat_enchantment_line(c) + f" (source: {src.replace('_', ' ')})" for src, c in unmatched]
    write(KB / "world" / "world-structures.md", "\n".join(lines))

    lines = ["# Cosmic happenings", ""]
    for c in sorted(cosmic, key=lambda c: (c.get("type", ""), c["name"])):
        lines += [f"## {c['name']}", "", f"({c.get('type')} {c.get('category')}, {c.get('duration')} turns)", "",
                  clean(c.get("description")), ""]
    write(KB / "world" / "cosmic-happenings.md", "\n".join(lines))
    write(KB / "world" / "_index.md", "# World\n\n- [Relics](relics.md)\n- [Free city factions](free-cities.md)\n"
          "- [World structures: ancient wonders, landmarks, magic materials](world-structures.md)\n"
          "- [Cosmic happenings](cosmic-happenings.md)")


# ---------------------------------------------------------------- spells

def build_spells():
    rows = []
    for sid, variants in sorted(spell_groups.items(), key=lambda kv: kv[1][0]["name"]):
        s = variants[0]
        tome = ", ".join(spell_tome.get(sid, []))
        kind = one_line(s.get("spellType"))
        rows.append([f"[{clean(s['name'])}]({slug(sid)}.md)", kind, one_line(s.get("casting_cost")),
                     one_line(s.get("upkeep")), tome, dlc(s)])
        lines = [f"# {clean(s['name'])}", "", f"- Type: {kind}",
                 f"- Casting cost: {one_line(s.get('casting_cost'))}"]
        if s.get("upkeep"):
            lines.append(f"- Upkeep: {one_line(s['upkeep'])}")
        if s.get("operation_point_cost"):
            lines.append(f"- Casting points: {s['operation_point_cost']}")
        if tome:
            lines.append(f"- Tome: {tome}")
        lines.append(f"- DLC: {dlc(s)}")
        req = names(s.get("enchantment_requisites"))
        if req:
            lines.append(f"- Applies to: {', '.join(req)}")
        summ = [unit_link(x.get("slug"), "../") if isinstance(x, dict) else str(x) for x in s.get("summoned_units", [])]
        if summ:
            lines.append(f"- Summons: {', '.join(summ)}")
        if len(variants) == 1:
            lines += ["", clean(s.get("description"))]
        else:  # one record per culture/subculture etc.; name each from its own text
            for v, label in zip(variants, variant_labels([clean(v.get("description")) for v in variants])):
                head = label.capitalize() if label.startswith("variant ") else f"Variant: {label}"
                lines += ["", f"## {head} (cost {one_line(v.get('casting_cost'))})", "", clean(v.get("description"))]
        write(KB / "spells" / f"{slug(sid)}.md", "\n".join(lines))
    write(KB / "spells" / "_index.md", "# Spells\n\n" + table(["Spell", "Type", "Cost", "Upkeep", "Tome", "DLC"], rows))


# ---------------------------------------------------------------- heroes

def skill_group(h, tree_of_group):
    """File group for a hero skill: its tree, else the tree its group belongs to (skills without a tree position
    sit in the same group as the tree's skills), else its group name."""
    group = clean(h.get("group_name"))
    if h.get("tree_name"):
        return clean(h["tree_name"])
    if group.startswith("Primal SubCulture"):
        return "Primal subculture avatars"
    if any(hero_skill_by_resid.get(r.get("resid"), {}).get("id", "").startswith("base_dragon_")
           for r in h.get("required_skills") or []):
        return "Dragon Lord"
    if not group and h.get("type") == "signature":
        return "Ruler signature skills"
    return tree_of_group.get(group) or group or "Other"


def build_heroes():
    tree_of_group = {clean(h["group_name"]): clean(h["tree_name"]) for h in hero_skills
                     if h.get("tree_name") and h.get("group_name")}
    classes = {c["name"]: c for c in faction if c["type"] == "Class"}
    groups = defaultdict(list)
    for h in hero_skills:
        # Nameless records are internal tree nodes (e.g. base_dragon_astral); the game's "Invalid Hero Skills"
        # group holds retired skills (ids end in _invalid, _disabled, _inactive, ...) that no live skill links to.
        if clean(h["name"]) and clean(h.get("group_name")) != "Invalid Hero Skills":
            groups[skill_group(h, tree_of_group)].append(h)
    idx = []
    for g, items in sorted(groups.items()):
        f = f"skills-{slug(g)}.md"
        lines = [f"# Hero skills: {g}", ""]
        entries = []
        if g in classes:
            lines += ["\n\n".join(loc_text(classes[g].get("extraLookup"), "description_short", "description")), ""]
        for h in sorted(items, key=lambda h: h["name"]):
            extra = [f"type {h['type']}"] if h.get("type") else []
            req, only = [], []
            for r in h.get("required_skills") or []:
                p = hero_skill_by_resid.get(r.get("resid"), {})
                dragon = re.fullmatch(r"base_dragon_(\w+)", p.get("id", ""))
                if dragon:  # hidden node that ties the skill to one Dragon Lord subtype
                    only.append(f"{AFFINITY_TAGS.get(dragon.group(1), dragon.group(1).capitalize())} Dragon")
                elif clean(p.get("name")):
                    req.append(clean(p["name"]))
            if only:
                extra.append(" or ".join(only) + " only")
            if req:  # the aow4db skill tree unlocks a skill once any one of its required skills is taken
                extra.append(("requires " if len(req) == 1 else "requires any of ") + ", ".join(req))
            excl = [clean(hero_skill_by_resid[e["resid"]]["name"]) for e in h.get("excluded_skills") or []
                    if e.get("resid") in hero_skill_by_resid]
            if excl:
                extra.append("can't be taken with " + ", ".join(excl))
            if h.get("id") in ascended_tomes:
                extra.append("granted by " + ", ".join(tome_ref(tome_by_name[n]) if n in tome_by_name else n
                                                       for n in ascended_tomes[h["id"]]))
            meta = f"({'; '.join(extra)}; DLC {dlc(h)})" if extra else f"(DLC {dlc(h)})"
            ab = [ability_line(a["slug"]) for a in h.get("abilities", []) if isinstance(a, dict) and a.get("slug")]
            ab = [a for a in ab if a]
            entries.append((clean(h["name"]), meta, "\n".join([clean(h.get("description"))] + (["\n".join(ab)] if ab else []))))
        entries = label_variants(unique(entries))  # same skill copied into several trees renders identically
        idx.append(f"- [{g}]({f}) ({len(entries)} skills)")
        write(KB / "heroes" / f, "\n".join(lines + [f"## {n}\n\n{m}\n\n{b}\n" for n, m, b in entries]))

    slots = defaultdict(list)
    for it in hero_items:
        if not it.get("id", "").endswith("_disabled"):  # retired item (a jagged Greataxe base)
            slots[it.get("slot") or "Other"].append(it)
    for slot_, items in sorted(slots.items()):
        f = f"items-{slug(slot_)}.md"
        lines = [f"# Hero items: {slot_}", ""]
        entries = []
        for it in sorted(items, key=lambda i: (i.get("tier_numerals", ""), i["name"])):
            meta = [it.get("tier", ""), f"DLC {dlc(it)}"]
            if it.get("hero_classes"):
                meta.append("classes: " + ", ".join(names(it["hero_classes"])))
            if it.get("hero_types"):
                meta.append("hero types: " + ", ".join(names(it["hero_types"])))
            if it.get("disabled_slots"):
                meta.append("disables slots: " + ", ".join(names(it["disabled_slots"])))
            ab = [ability_line(a["slug"] if isinstance(a, dict) else a) for a in it.get("ability_slugs", [])]
            ab = [a for a in ab if a]
            entries.append((clean(it["name"]), f"({'; '.join(m for m in meta if m)})",
                            "\n".join([clean(it.get("description"))] + (["\n".join(ab)] if ab else []))))
        entries = label_variants(unique(entries))  # base types per culture/hero type (Ring, Crown, ...) render identically
        idx.append(f"- [{slot_} items]({f}) ({len(entries)} items)")
        write(KB / "heroes" / f, "\n".join(lines + [f"## {n}\n\n{m}\n\n{b}\n" for n, m, b in entries]))

    lines = ["# Hero destinies", ""]
    for d in destinies:
        who = {(True, True): "rulers and heroes", (False, True): "heroes only (not rulers)",
               (True, False): "rulers only", (False, False): "neither rulers nor heroes, per the game data"}
        avail = who[(bool(d.get("available_to_rulers")), bool(d.get("available_to_non_rulers")))]
        lines += [f"## {clean(d['name'])}", "", f"Available to: {avail}", "", clean(d.get("screen_description"))]
        for a in d.get("ambitions", []):
            rew = [f"{clean(p.get('name'))}: {one_line(p.get('screen_description'))}" for p in a.get("reward_properties", [])]
            if a.get("reward_renown"):
                rew.append(f"+{a['reward_renown']} Renown")
            rep = ", repeatable" if a.get("repeatable") else ""
            lines.append(f"- {a.get('type', '')} ambition{rep}: {one_line(a.get('screen_description'))} -> {join_items(rew)}")
        lines.append("")
    write(KB / "heroes" / "destinies.md", "\n".join(lines))
    idx.append("- [Hero destinies](destinies.md)")
    write(KB / "heroes" / "_index.md", "# Heroes\n\n" + "\n".join(idx))


# ---------------------------------------------------------------- empire-wide

def build_empire():
    lines = ["# Empire progression (empire skills)", ""]
    # Records without a category are the skill-tree category headers themselves (General, Astral Affinity, ...).
    for cat in sorted({p["category"] for p in progression if p.get("category")}):
        lines += [f"## {cat}", ""]
        for p in sorted((p for p in progression if p.get("category", "") == cat), key=lambda p: (p.get("required_level", 0), p["name"])):
            req = [f"level {p['required_level']}" if p.get("required_level") else "",
                   one_line(p.get("required_affinity")), f"cost {one_line(p.get('cost'))}" if p.get("cost") else ""]
            if p.get("repeat_cost_increase"):  # its `cooldown` field always equals required_xp, so it's left out
                req.append(f"repeatable, each repeat costs +{one_line(p['repeat_cost_increase'])}")
            lines.append(f"- **{clean(p['name'])}** ({', '.join(r for r in req if r)}): {one_line(p.get('description'))}")
        lines.append("")
    write(KB / "empire" / "empire-progression.md", "\n".join(lines))

    entries = []
    for g in governance:
        # The description repeats level_data as a bullet list; keep only the text around that list.
        desc = re.sub(r"<bulletlist>.*?</bulletlist>", "\n", g.get("screen_description") or "", flags=re.S)
        levels = [f"- Renown level {l.get('level')}: {one_line(l.get('effect_description'))}" for l in g.get("level_data", [])]
        entries.append((clean(g["name"]), clean(desc), "\n".join(levels)))
    write(KB / "empire" / "governance.md", "\n".join(["# Governors (governance)", ""] + [
        f"## {n}\n\n{d}\n{lv}\n" for n, d, lv in label_variants(entries)]))

    lines = ["# City structures and upgrades", "",
             "- category: the province improvement or victory type the structure counts as (from the icon in its name).",
             "- Requires: the game's own build requirement text.",
             "- Unlocked by: tome whose research or pick unlocks the structure (tier 0 = culture/subculture tome, pact "
             "or special research).",
             "- Built after: its parent in the city building tree (aow4db GEN/CityTree.json); 'or' separates alternatives "
             "(Wizard Tower vs Vampire Castle).",
             "- Boost requirements: game data field, named as on the aow4db site; what the boost gives isn't in the data.",
             f"- Culture building: from the {CULTURE_MAP_NOTE} (aow4db HTML/CityTrees.html).", ""]
    variants = []
    for vs in dedupe(structures).values():
        labels = variant_labels([f"{one_line(v.get('requirement_description'))}\n{clean(v.get('description'))}"
                                 for v in vs]) if len(vs) > 1 else [""]
        variants += [(v, n, lab) for n, (v, lab) in enumerate(zip(vs, labels), 1)]
    for s, n, label in sorted(variants, key=lambda x: (x[0]["name"], x[1])):
        sid = s["id"]
        title = clean(s["name"]) + (f" ({label})" if label else "")
        meta = [f"cost {one_line(s.get('cost'))}" if s.get("cost") else "", f"DLC {dlc(s)}",
                "province/sector upgrade" if s.get("is_sector_upgrade") else "",
                f"category: {s['category']}" if s.get("category") else ""]
        req = one_line(s.get("requirement_description"))
        info = []
        if structure_tomes.get(sid):
            info.append("Unlocked by: " + ", ".join(tome_ref(t) for t in structure_tomes[sid]))
        built = [" or ".join(sorted(clean(structure_by_id[p]["name"]) for p in city_after.get(sid, ())))]
        built += [f"City Tier {t}" for t in sorted(city_tiers.get(sid, ()), key=CITY_TIERS.index)]
        if any(built):
            info.append("Built after: " + " and ".join(b for b in built if b))
        if s.get("boost_requirements"):
            info.append("Boost requirements: " + one_line(s["boost_requirements"]))
        for full, culture, what, base in culture_building_of.get(sid, []):
            after = culture_built_after(full, culture, base)
            info.append(f"Culture building ({CULTURE_MAP_NOTE}): [{full}](../cultures/{slug(culture)}.md), {what}"
                        + (f"; built after {after}" if after else ""))
        lines += [f"## {title}", "", f"({'; '.join(m for m in meta if m)})" + (f" Requires: {req}" if req else "")]
        lines += [f"- {i}" for i in info] + ([""] if info else [])
        lines += [clean(s.get("description")) or clean(s.get("prediction_description")), ""]
    write(KB / "empire" / "structures.md", "\n".join(lines))

    lines = ["# Siege projects", ""]
    for s in siege:
        unlock = "available by default"
        if s.get("needs_research_to_unlock"):
            by = siege_tomes.get(s.get("id"))
            unlock = "unlocked by " + ", ".join(tome_ref(t) for t in by) if by else "needs research"
        lines.append(f"- **{clean(s['name'])}** (cost {one_line(s.get('cost'))}, fortification damage {s.get('siege_health_damage')}, "
                     f"{unlock}, DLC {dlc(s)}): {one_line(s.get('description'))}")
    write(KB / "empire" / "siege-projects.md", "\n".join(lines))

    lines = ["# Item forge", "",
             "Needs = magic materials required to unlock it. Fits = item types the upgrade can go on (from the game's tag "
             "filter; 'lacks X' = the item must not carry tag X).", "", "## Item types", ""]
    types = []
    for f in sorted(forge_types, key=lambda f: (f.get("slot", ""), f["name"])):
        needs = token_needs(f.get("unlock_requirements"))
        types.append(f"- **{clean(f['name'])}** ({f.get('slot', '')}, DLC {dlc(f)}{', needs ' + needs if needs else ''}): "
                     f"{one_line(f.get('description'))}")
    lines += unique(types) + ["", "## Upgrades", ""]  # one record per culture/hero type, identical text
    upgrades = []
    for f in sorted(forge_upgrades, key=lambda f: f["name"]):
        meta = [f"{f.get('point_cost')} pts", f"DLC {dlc(f)}"]
        if f.get("unlock_requirements"):
            meta.append("needs " + token_needs(f["unlock_requirements"]))
        if f.get("tag_filter"):
            meta.append("fits " + tag_filter(f["tag_filter"]))
        upgrades.append(f"- **{clean(f['name'])}** ({', '.join(meta)}): {one_line(f.get('description'))}")
    write(KB / "empire" / "item-forge.md", "\n".join(lines + unique(upgrades)))
    write(KB / "empire" / "_index.md", "# Empire-wide systems\n\n"
          "- [Empire progression / empire skills](empire-progression.md)\n- [Governors](governance.md)\n"
          "- [City structures and upgrades](structures.md)\n- [Siege projects](siege-projects.md)\n- [Item forge](item-forge.md)")


def build_glossary():
    lines = ["# Glossary (in-game concept tooltips)", ""]
    for c in sorted(concepts.values(), key=lambda c: c.get("name") or ""):
        if c.get("name"):
            lines.append(f"- **{clean(c['name'])}**: {one_line(c.get('description'))}")
    write(KB / "glossary.md", "\n".join(lines))


def build_status_effects():
    """StatusEffects.json lists slugs only; the name and text live in Abilities.json."""
    seen = set()
    for s in load("StatusEffects"):
        a = abilities.get(s["slug"].lower())
        if a and a.get("name"):
            seen.add((clean(a["name"]), one_line(a.get("description"))))
    lines = ["# Status effects", "",
             "What each combat status effect does (in-game tooltip text). Same-name lines are variants.", ""]
    lines += [f"- **{name}**: {desc}" for name, desc in sorted(seen)]
    write(KB / "status-effects.md", "\n".join(lines))


def build_source():
    try:
        rev = subprocess.run(["git", "-C", str(SRC_REPO), "log", "-1", "--format=%h %cd", "--date=short"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        rev = "unknown"
    write(KB / "SOURCE.md", f"# Source\n\nGenerated from aow4db (github.com/MinionsArt/aow4db) commit {rev}, Data/EN.\n"
          "Regenerate: `git -C ../aow4db pull` then `python build_kb.py`.")


if __name__ == "__main__":
    for g in GENERATED:
        p = KB / g
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    build_tomes()
    build_traits()
    culture_units = build_units()
    build_cultures(culture_units)
    build_races()
    build_rulers()
    build_world()
    build_spells()
    build_heroes()
    build_empire()
    build_glossary()
    build_status_effects()
    build_source()
    files = list(KB.rglob("*.md"))
    print(f"Generated {len(files)} files, {sum(f.stat().st_size for f in files) // 1024} KB")
