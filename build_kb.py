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
GENERATED = ["tomes", "traits", "units", "spells", "cultures", "heroes", "empire", "glossary.md", "SOURCE.md"]

# ---------------------------------------------------------------- markup cleanup

# Labels for icon tags like 12<gold></gold>. "" = drop (the text around it already says it).
ICON_LABELS = {
    "gold": "Gold", "mana": "Mana", "unitprod": "Draft", "structureprod": "Production",
    "influence": "Imperium", "knowledge": "Knowledge", "food": "Food",
    "souls": "Souls", "population": "Population", "thralls": "Thralls", "hp": "HP",
    "temphp": "Temporary HP", "defense": "Defense", "resistance": "Resistance",
    "statuseffectresistance": "Status Resistance", "crit": "Crit", "xp": "XP", "turn": "Turns",
    "conduit": "Conduit", "optactical": "Combat Casting Points",
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


def clean(s):
    if not s:
        return ""
    s = str(s).replace('\\"', '"').replace("\\n", "\n")
    s = re.sub(r"<span[^>]*>|</span>", "", s)
    s = re.sub(r"</?hyperlink>|</?helpcolor>|</?\w+Col>", "", s)
    s = re.sub(r"<br\s*/?>(</br>)?", "\n", s)
    s = s.replace("<bulletlist>", "\n").replace("</bulletlist>", "\n")
    s = s.replace("<bullet>", "\n- ").replace("</bullet>", "")

    def icon(m):
        num, tag, nxt = m.group(1), m.group(2), m.group(3).lower()
        label = icon_label(tag)
        if nxt and nxt.startswith(label.lower()[:4]):
            label = ""  # following text already names it ("3 <turn></turn> Turns")
        if num:
            return f"{num} {label} "
        return f" {label} " if label else " "

    # Icon tags like 12<gold></gold>; peek (without consuming) at the next word to avoid "Food Food".
    s = re.sub(r"(?:([+-]?\d+%?)\s*)?<(\w+)></\2>(?=\s*([^\s<]*))", icon, s)
    s = re.sub(r" +([.,;:)])", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def one_line(s, n=None):
    s = clean(s).replace("\n- ", "; ").replace("\n", " ")
    s = s.replace("|", "/")
    return s if n is None or len(s) <= n else s[: n - 1].rstrip() + "…"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "unnamed"


def dlc(x):
    return (x.get("DLC") or "").strip() or "Base"


def tome_affinity(s):
    parts = re.findall(r"(\d+)\s*<empire(\w+)>", s or "")
    return ", ".join(f"{AFFINITY_TAGS.get(a, a.capitalize())} {n}" for n, a in parts)


def trait_affinity(lst):
    out = []
    for a in lst or []:
        m = re.match(r"(\d+)\s*<(\w+)>", a.get("name", ""))
        out.append(f"{AFFINITY_TAGS.get(m.group(2), m.group(2))} {m.group(1)}" if m else clean(a.get("name")))
    return ", ".join(out)


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


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def load(name):
    return json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


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

tomes = load("Tomes")
for _t in tomes:  # tier 0 = culture/subculture tomes, pacts and other non-research tomes
    _t["tier"] = _t.get("tier") or 0
    _t["name"] = _t.get("name") or _t["id"].replace("_", " ").title()
traits = load("Traits")
units = load("Units")
spells = load("Spells")
abilities = {a["slug"].lower(): a for a in load("Abilities")}
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

unit_groups = dedupe(units)
spell_groups = dedupe(spells)
structure_by_id = {s["id"]: s for s in structures}
hero_skill_by_id = {h["id"]: h for h in hero_skills}

unit_tome, spell_tome = defaultdict(list), defaultdict(list)
for t in tomes:
    for sk in t.get("skills", []):
        if sk.get("unit_slug"):
            unit_tome[sk["unit_slug"]].append(t["name"])
        if sk.get("spell_slug"):
            spell_tome[sk["spell_slug"]].append(t["name"])


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
    text = " ".join(one_line(b) for b in body if b)
    return f"- {head}: {text}" if text else f"- {head}"


# ---------------------------------------------------------------- tomes

def build_tomes():
    rows = []
    for t in sorted(tomes, key=lambda t: (t["tier"], tome_affinity(t.get("affinities")), t["name"])):
        aff = tome_affinity(t.get("affinities"))
        rows.append([f"[{t['name']}]({slug(t['id'])}.md)", t["tier"], aff, dlc(t), one_line(t.get("gameplay_description"))])
        lines = [f"# {t['name']}", "",
                 f"- Tier: {t['tier']}", f"- Affinity granted: {aff}", f"- DLC: {dlc(t)}", "",
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
    headers = ["Tome", "Tier", "Affinity", "DLC", "Summary"]
    write(KB / "tomes" / "_index.md", "# Tomes\n\n"
          "Affinity = affinity points the tome grants. Tier N+1 unlocks after enough tomes of tier N.\n\n"
          "## Magic tomes (researchable, tiers 1-5)\n\n" + table(headers, [r for r in rows if r[1]])
          + "\n\n## Tier 0: culture/subculture tomes, pacts and other non-research tomes\n\n"
          "Culture tomes (named 'Culture - Subculture') hold what that culture/subculture unlocks.\n\n"
          + table(headers, [r for r in rows if not r[1]]))


# ---------------------------------------------------------------- traits

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
                         "; ".join(effects)])
            lines = [f"# {name}{evil}", "", f"- Type: {typ} trait", f"- Point cost: {t.get('point_cost', '')}"]
            if t.get("group_name"):
                lines.append(f"- Group: {t['group_name']}")
            if aff:
                lines.append(f"- Affinity: {aff}")
            lines.append(f"- DLC: {dlc(t)}")
            if not t.get("enabled", True):
                lines.append("- Note: disabled in game data")
            inc = names(t.get("incompatible_society_traits"))
            if inc:
                lines.append(f"- Incompatible with: {', '.join(inc)}")
            lines += ["", "## Effects", ""] + [f"- {e}" for e in effects]
            sb = names(t.get("starting_bonuses"))
            if sb:
                lines += ["", "## Starting bonus", ""] + [f"- {b}" for b in sb]
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
            ab = [ability_line(a["slug"]) for a in u.get(key, [])]
            ab = [a for a in ab if a]
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

    lines = ["# Cultures and subcultures", "",
             "There are no dedicated culture records. Culture/subculture unlocks live in tier-0 tomes (below);",
             "culture units are derived from units data. Starting affinity is not in the data.", "",
             "## Culture, subculture and special tomes (tier 0)", ""]
    lines += [f"- [{t['name']}](../tomes/{slug(t['id'])}.md)" for t in sorted(tomes, key=lambda t: t["name"]) if not t["tier"]]
    lines += ["", "# Culture units by subculture", ""]
    for c in sorted(cultures):
        lines += [f"## {c}", ""]
        for sc in sorted(cultures[c]):
            lines.append(f"- {sc}: " + ", ".join(unit_link(uid, "../") for uid in cultures[c][sc]))
        lines.append("")
    write(KB / "cultures" / "_index.md", "\n".join(lines))


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
        lines += ["", clean(s.get("description"))]
        for v in variants[1:]:
            lines += ["", f"## Variant (cost {one_line(v.get('casting_cost'))})", "", clean(v.get("description"))]
        write(KB / "spells" / f"{slug(sid)}.md", "\n".join(lines))
    write(KB / "spells" / "_index.md", "# Spells\n\n" + table(["Spell", "Type", "Cost", "Upkeep", "Tome", "DLC"], rows))


# ---------------------------------------------------------------- heroes

def build_heroes():
    groups = defaultdict(list)
    for h in hero_skills:
        groups[clean(h.get("tree_name") or h.get("group_name") or "Other")].append(h)
    idx = []
    for g, items in sorted(groups.items()):
        f = f"skills-{slug(g)}.md"
        idx.append(f"- [{g}]({f}) ({len(items)} skills)")
        lines = [f"# Hero skills: {g}", ""]
        for h in sorted(items, key=lambda h: h["name"]):
            extra = [f"type {h['type']}"] if h.get("type") else []
            if h.get("required_skills"):
                extra.append("requires " + ", ".join(clean(hero_skill_by_id.get(r.get("slug"), {}).get("name", r.get("slug", ""))) for r in h["required_skills"]))
            lines.append(f"## {clean(h['name'])}\n\n" + (f"({'; '.join(extra)}; DLC {dlc(h)})\n\n" if extra else f"(DLC {dlc(h)})\n\n")
                         + clean(h.get("description")))
            ab = [ability_line(a["slug"]) for a in h.get("abilities", []) if isinstance(a, dict) and a.get("slug")]
            ab = [a for a in ab if a]
            if ab:
                lines.append("\n".join(ab))
            lines.append("")
        write(KB / "heroes" / f, "\n".join(lines))

    slots = defaultdict(list)
    for it in hero_items:
        slots[it.get("slot") or "Other"].append(it)
    for slot_, items in sorted(slots.items()):
        f = f"items-{slug(slot_)}.md"
        idx.append(f"- [{slot_} items]({f}) ({len(items)} items)")
        lines = [f"# Hero items: {slot_}", ""]
        for it in sorted(items, key=lambda i: (i.get("tier_numerals", ""), i["name"])):
            meta = [it.get("tier", ""), f"DLC {dlc(it)}"]
            if it.get("hero_classes"):
                meta.append("classes: " + ", ".join(names(it["hero_classes"])))
            lines.append(f"## {clean(it['name'])}\n\n({'; '.join(m for m in meta if m)})\n\n{clean(it.get('description'))}")
            ab = [ability_line(a) for a in it.get("ability_slugs", []) if isinstance(a, str)]
            ab = [a for a in ab if a]
            if ab:
                lines.append("\n".join(ab))
            lines.append("")
        write(KB / "heroes" / f, "\n".join(lines))

    lines = ["# Hero destinies", ""]
    for d in destinies:
        lines += [f"## {clean(d['name'])}", "", clean(d.get("screen_description"))]
        for a in d.get("ambitions", []):
            rew = "; ".join(f"{clean(p.get('name'))}: {one_line(p.get('screen_description'))}" for p in a.get("reward_properties", []))
            lines.append(f"- {a.get('type', '')} ambition: {one_line(a.get('screen_description'))} -> {rew}")
        lines.append("")
    write(KB / "heroes" / "destinies.md", "\n".join(lines))
    idx.append("- [Hero destinies](destinies.md)")
    write(KB / "heroes" / "_index.md", "# Heroes\n\n" + "\n".join(idx))


# ---------------------------------------------------------------- empire-wide

def build_empire():
    lines = ["# Empire progression (empire skills)", ""]
    for cat in sorted({p.get("category", "") for p in progression}):
        lines += [f"## {cat}", ""]
        for p in sorted((p for p in progression if p.get("category", "") == cat), key=lambda p: (p.get("required_level", 0), p["name"])):
            req = [f"level {p['required_level']}" if p.get("required_level") else "",
                   one_line(p.get("required_affinity")), f"cost {one_line(p.get('cost'))}" if p.get("cost") else ""]
            lines.append(f"- **{clean(p['name'])}** ({', '.join(r for r in req if r)}): {one_line(p.get('description'))}")
        lines.append("")
    write(KB / "empire" / "empire-progression.md", "\n".join(lines))

    lines = ["# Governors (governance)", ""]
    for g in governance:
        lines += [f"## {clean(g['name'])}", "", clean(g.get("screen_description"))]
        lines += [f"- Level {l.get('level')}: {one_line(l.get('effect_description'))}" for l in g.get("level_data", [])]
        lines.append("")
    write(KB / "empire" / "governance.md", "\n".join(lines))

    lines = ["# City structures and upgrades", ""]
    for s in sorted(structures, key=lambda s: s["name"]):
        meta = [f"cost {one_line(s.get('cost'))}" if s.get("cost") else "", f"DLC {dlc(s)}",
                "province/sector upgrade" if s.get("is_sector_upgrade") else ""]
        req = one_line(s.get("requirement_description"))
        lines += [f"## {clean(s['name'])}", "", f"({'; '.join(m for m in meta if m)})" + (f" Requires: {req}" if req else ""),
                  clean(s.get("description")) or clean(s.get("prediction_description")), ""]
    write(KB / "empire" / "structures.md", "\n".join(lines))

    lines = ["# Siege projects", ""]
    for s in siege:
        lines.append(f"- **{clean(s['name'])}** (cost {one_line(s.get('cost'))}, fortification damage {s.get('siege_health_damage')}, "
                     f"{'needs research' if s.get('needs_research_to_unlock') else 'available by default'}, DLC {dlc(s)}): {one_line(s.get('description'))}")
    write(KB / "empire" / "siege-projects.md", "\n".join(lines))

    lines = ["# Item forge", "", "## Item types", ""]
    for f in sorted(forge_types, key=lambda f: (f.get("slot", ""), f["name"])):
        lines.append(f"- **{clean(f['name'])}** ({f.get('slot', '')}, DLC {dlc(f)}): {one_line(f.get('description'))}")
    lines += ["", "## Upgrades", ""]
    for f in sorted(forge_upgrades, key=lambda f: f["name"]):
        lines.append(f"- **{clean(f['name'])}** ({f.get('point_cost')} pts, DLC {dlc(f)}): {one_line(f.get('description'))}")
    write(KB / "empire" / "item-forge.md", "\n".join(lines))
    write(KB / "empire" / "_index.md", "# Empire-wide systems\n\n"
          "- [Empire progression / empire skills](empire-progression.md)\n- [Governors](governance.md)\n"
          "- [City structures and upgrades](structures.md)\n- [Siege projects](siege-projects.md)\n- [Item forge](item-forge.md)")


def build_glossary():
    lines = ["# Glossary (in-game concept tooltips)", ""]
    for c in sorted(concepts.values(), key=lambda c: c.get("name") or ""):
        if c.get("name"):
            lines.append(f"- **{clean(c['name'])}**: {one_line(c.get('description'))}")
    write(KB / "glossary.md", "\n".join(lines))


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
    build_units()
    build_spells()
    build_heroes()
    build_empire()
    build_glossary()
    build_source()
    files = list(KB.rglob("*.md"))
    print(f"Generated {len(files)} files, {sum(f.stat().st_size for f in files) // 1024} KB")
