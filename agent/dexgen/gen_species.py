"""Emit species.json for the web Pokedex from rowe-v2.1b.gba.

Read-only on the ROM. Reuses rowe_rom.py for the species, evolution and wild
structures; adds the one table rowe_rom does not expose, the species-name table.

Name table: a standalone block at 0x40B558, 13 bytes per name, 0xFF terminated,
indexed by national dex id. Found by fingerprinting Bulbasaur (id 1) at 0x40B565
and Charmander (id 4) at 0x40B58C, 0x27 apart over 3 ids, and confirmed against
Seaking (id 119) at 0x40BB63; the block ends exactly at MOVE_NAMES_OFFSET
(0x4118D3). Base names (ids 1-1025) truncate at 10 chars, form names (1501+) carry
up to 12, so form-to-base matching compares the first 10 chars.

Wild header layout is the RoweSource struct WildPokemonHeader: a u8 group, u8 num,
then seven WildPokemonInfo pointers in order land, land-night, water, rock-smash,
fishing, hidden, headbutt, with 12/12/5/5/10/3/3 slots. The fishing block splits
into old (0-1), good (2-4) and super (5-9) rod by RoweSource ChooseWildMonIndex_Fishing.

The gate on each encounter row classifies the evolution path from the slot species up to the record
by RoweSource GetWildPokemon()'s method groups (src/level_scaling.c). Its friendship (level 24) and
badge (5 midgame, 7 lategame) thresholds are read from the 1.9.4 source and are approximate against
the 2.1b binary; a multi-step level path reports the first step, the level the slot leaves its base.
"""
import hashlib
import json
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rowe_rom as R  # noqa: E402

NAME_OFFSET = 0x40B558
NAME_STRIDE = 13
DEX_MAX = 1025          # ids 1..DEX_MAX are national dex base species
FORM_START = 1501       # ids FORM_START..SPECIES_COUNT-1 are ROWE's forms
LIVE_DIR = "/var/www/brenergy/live"
MAPS_JSON = os.path.join(LIVE_DIR, "maps.json")
ICONS_SHEET = os.path.join(LIVE_DIR, "icons-sheet.json")
LIVE_PATH = os.path.join(LIVE_DIR, "species.json")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "species.json")

# struct WildPokemonHeader pointer order and slot counts (RoweSource include/wild_encounter.h)
WILD_PTRS = [
    ("land", 12),
    ("land_night", 12),
    ("surf", 5),
    ("rock_smash", 5),
    ("fishing", 10),
    ("hidden", 3),
    ("headbutt", 3),
]
# fishing slot -> rod method (RoweSource ChooseWildMonIndex_Fishing)
ROD_METHOD = {0: "old_rod", 1: "old_rod", 2: "good_rod", 3: "good_rod", 4: "good_rod",
              5: "super_rod", 6: "super_rod", 7: "super_rod", 8: "super_rod", 9: "super_rod"}


def species_name(species_id):
    o = NAME_OFFSET + species_id * NAME_STRIDE
    return R._decode(R._rom()[o:o + NAME_STRIDE]).strip()


def wild_header_base():
    """Start offset of gWildMonHeaders, the longest run of valid headers at the ROWE
    stride, the same way rowe_rom.wild_land_levels locates it."""
    rom = R._rom()
    s = R.WILD_HEADER_STRIDE
    best_start, best_run, o = 0, 0, 0
    while o + s <= len(rom):
        if R._wild_header_valid(o) and (o < s or not R._wild_header_valid(o - s)):
            run, q = 0, o
            while R._wild_header_valid(q):
                run += 1
                q += s
            if run > best_run:
                best_start, best_run = o, run
        o += 4
    return best_start, best_run


def info_slots(info_ptr, count):
    """[(slot_index, min, max, species)] of a WildPokemonInfo's first `count` slots,
    species 0 dropped; () when the pointer or its array is off-ROM. The slot index is
    kept so the fishing block can split into old/good/super rod."""
    rom = R._rom()
    if not R._in_rom(info_ptr):
        return ()
    mons = struct.unpack_from("<I", rom, info_ptr - R.ROM_BASE + 4)[0]
    if not R._in_rom(mons) or not R._in_rom(mons + count * 4):
        return ()
    out = []
    for k in range(count):
        mn, mx, sp = struct.unpack_from("<BBH", rom, mons - R.ROM_BASE + k * 4)
        if sp and sp < R.SPECIES_COUNT:
            out.append((k, mn, mx, sp))
    return out


def map_encounters():
    """{(group, num): {method: [(min, max, species)]}} over every wild header."""
    rom = R._rom()
    base, run = wild_header_base()
    out = {}
    for i in range(run):
        h = base + i * R.WILD_HEADER_STRIDE
        g, num = rom[h], rom[h + 1]
        ptrs = struct.unpack_from("<7I", rom, h + R.WILD_LAND_PTR)
        methods = {}
        for (name, count), ptr in zip(WILD_PTRS, ptrs):
            if ptr == 0:
                continue
            for k, mn, mx, sp in info_slots(ptr, count):
                method = ROD_METHOD[k] if name == "fishing" else name
                methods.setdefault(method, []).append((mn, mx, sp))
        out[(g, num)] = methods
    return out


def form_base_map():
    """{form_id: base_national_id} by matching a form's 10-char name to a base's."""
    base_by_name = {}
    for i in range(1, DEX_MAX + 1):
        base_by_name.setdefault(species_name(i)[:10], i)
    forms, unresolved = {}, []
    for f in range(FORM_START, R.SPECIES_COUNT):
        n = species_name(f)
        if not n:
            continue
        b = base_by_name.get(n[:10])
        if b is None:
            unresolved.append((f, n))
        else:
            forms[f] = b
    return forms, unresolved


def evo_closure(species_id):
    """{species_id} and every species it evolves into, over all evolution methods."""
    seen, stack = {species_id}, [species_id]
    while stack:
        s = stack.pop()
        for _method, _param, target in R.evolutions(s):
            if target and target < R.SPECIES_COUNT and target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


# gEvolutionTable method ids (RoweSource include/constants/pokemon.h) grouped the way
# GetWildPokemon() gates a slot's climb (src/level_scaling.c): friendship-family levels at 24,
# midgame at 5 badges, lategame at 7, level-family at the row's own param.
EVO_LEVEL_METHODS = {4, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 28, 30, 35, 36, 37, 40, 41, 42}
EVO_FRIENDSHIP_METHODS = {1, 2, 3, 21}
EVO_MIDGAME_METHODS = {15, 22, 29}
EVO_LATEGAME_METHODS = {5, 6, 7, 23, 25, 26, 27}
FRIENDSHIP_LEVEL = 24
BADGES_MIDGAME = 5
BADGES_LATEGAME = 7


def evo_path(src, dst):
    """The (method, param) steps from src to dst, or None when dst is unreachable; [] when equal.
    Lines are short and acyclic, so a per-branch visited set is enough to guard a shared target."""
    if src == dst:
        return []

    def walk(node, path, seen):
        for method, param, target in R.evolutions(node):
            if not target or target >= R.SPECIES_COUNT or target in seen:
                continue
            step = path + [(method, param)]
            if target == dst:
                return step
            found = walk(target, step, seen | {target})
            if found is not None:
                return found
        return None

    return walk(src, [], {src})


def classify_gate(steps):
    """The gate the page renders for an evolution path: None for a direct slot, {badges} when any
    step is badge-gated (the strictest count), {level} for a level/friendship climb (the first
    step, the level the slot leaves its base form), {kind: 'other'} when no step carries a number."""
    if not steps:
        return None
    badges, levels = [], []
    for method, param in steps:
        if method in EVO_MIDGAME_METHODS:
            badges.append(BADGES_MIDGAME)
        elif method in EVO_LATEGAME_METHODS:
            badges.append(BADGES_LATEGAME)
        elif method in EVO_FRIENDSHIP_METHODS:
            levels.append(FRIENDSHIP_LEVEL)
        elif method in EVO_LEVEL_METHODS and param:
            levels.append(param)
    if badges:
        return {"badges": max(badges)}
    if levels:
        return {"level": levels[0]}
    return {"kind": "other"}


def gate_cost(gate):
    """Order gates easiest-first so a merge over several slots keeps the most direct way the record
    appears: a direct slot, then the lowest level, then badges, then an unnumbered route."""
    if gate is None:
        return -1
    if "level" in gate:
        return gate["level"]
    if "badges" in gate:
        return 100 + gate["badges"]
    return 10000


def main():
    rom_sha = hashlib.sha256(R._rom()).hexdigest()
    with open(MAPS_JSON) as f:
        maps = json.load(f)

    form_base, unresolved_forms = form_base_map()
    forms_of = {}
    for form_id, base_id in form_base.items():
        forms_of.setdefault(base_id, []).append(form_id)

    def base_of(sp):
        if 1 <= sp <= DEX_MAX:
            return sp
        return form_base.get(sp)

    # accumulate encounters: {base_id: {(map_name, method): row}}, row holding the merged level
    # span plus the slot species (via) and its evolution gate to this record
    enc = {}
    unresolved_wild = set()
    for (g, num), methods in map_encounters().items():
        map_name = maps.get(f"{g}/{num}", f"{g}/{num}")
        for method, slots in methods.items():
            for lo, hi, sp in slots:
                for d in evo_closure(sp):
                    b = base_of(d)
                    if b is None:
                        unresolved_wild.add(d)
                        continue
                    steps = evo_path(sp, d) or []
                    gate = classify_gate(steps)
                    via = base_of(sp) or sp
                    key = (map_name, method)
                    cur = enc.setdefault(b, {}).get(key)
                    if cur is None:
                        enc[b][key] = {"lo": lo, "hi": hi, "via": via, "gate": gate, "plen": len(steps)}
                    else:
                        cur["lo"], cur["hi"] = min(cur["lo"], lo), max(cur["hi"], hi)
                        if (len(steps), gate_cost(gate)) < (cur["plen"], gate_cost(cur["gate"])):
                            cur.update(via=via, gate=gate, plen=len(steps))

    records = []
    gate_hist = {"direct": 0, "level": 0, "badges": 0, "other": 0}
    for i in range(1, DEX_MAX + 1):
        rows = []
        for (m, meth), e in sorted(enc.get(i, {}).items()):
            rows.append({"map": m, "method": meth, "levels": [e["lo"], e["hi"]],
                         "via": e["via"], "gate": e["gate"]})
            key = "direct" if e["gate"] is None else next(iter(e["gate"])) if "kind" not in e["gate"] else "other"
            gate_hist[key] += 1
        sp = R.species(i)
        t0, t1 = sp.types
        types = [R.TYPE_NAMES[t0]] + ([R.TYPE_NAMES[t1]] if t1 != t0 else [])
        bs = sp.base_stats
        stats = {"hp": bs[R.HP], "atk": bs[R.ATK], "def": bs[R.DEF],
                 "spa": bs[R.SPA], "spd": bs[R.SPD], "spe": bs[R.SPE]}
        records.append({
            "id": i,
            "name": species_name(i),
            "forms": [{"id": f, "name": species_name(f)} for f in sorted(forms_of.get(i, []))],
            "encounters": rows,
            "no_wild": not rows,
            "types": types,
            "stats": stats,
        })

    with open(ICONS_SHEET) as f:
        sheet_count = json.load(f)["count"]
    assert len(records) == DEX_MAX, f"expected {DEX_MAX} records, got {len(records)}"
    assert len(records) == sheet_count, f"record count {len(records)} != icons-sheet count {sheet_count}"

    with open(OUT_PATH, "w") as f:
        json.dump({"rom_sha": rom_sha, "species": records}, f, separators=(",", ":"))
    shutil.copy(OUT_PATH, LIVE_PATH)

    base_count = len(records)
    form_count = sum(len(r["forms"]) for r in records)
    with_enc = sum(1 for r in records if not r["no_wild"])
    print(f"wrote {OUT_PATH} and {LIVE_PATH}")
    print(f"rom_sha {rom_sha}")
    print(f"base records {base_count}, form records {form_count}")
    print(f"with encounters {with_enc}, no_wild {base_count - with_enc}")
    print("gate histogram: " + ", ".join(f"{k} {gate_hist[k]}" for k in ("direct", "level", "badges", "other")))
    print(f"unresolved form names {len(unresolved_forms)}: {unresolved_forms}")
    print(f"unresolved wild species {sorted(unresolved_wild)}")


if __name__ == "__main__":
    main()
