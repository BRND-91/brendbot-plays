"""Extract ROWE's static game data from the ROM into games/rowe/rowe_rom.db.

Every value comes from rowe_rom's readers, so the db is a queryable snapshot of the same
tables the battle engine and planner read at runtime: species base stats and types, move
power/type/category, the type chart, abilities, level-up and TM and egg learnsets,
evolutions, wild encounter levels, the gym-leader and League rosters, item prices, and the
world map: every map's layout and music ids, its gym/center/mart classification, its warps,
its overworld connections, and its object templates. The map tables are what a route or a
gym-location query reads instead of a hand-list, so (2,9) resolves to real ROM data.

Species are keyed by national-dex id and maps by (grp, num); the ROM reader exposes no
species-name or map-name string, so neither is stored.

    build_rom_db.py [out.db]
"""
import sqlite3
import struct
import sys

import rowe_rom as R

TYPE = R.TYPE_NAMES
CATEGORY = {R.SPLIT_PHYSICAL: "Physical", R.SPLIT_SPECIAL: "Special", R.SPLIT_STATUS: "Status"}


def ability(aid: int) -> str:
    return R.ability_name(aid) if aid else ""


def move_name(mv: int) -> str | None:
    # learnsets and egg tables reference moves past MOVE_COUNT, the last named row; those ids
    # are stored with a null name rather than widening the name table on a guess
    return R.move(mv).name if mv < R.MOVE_COUNT else None


def real_species() -> list[int]:
    out = []
    for sid in range(1, R.SPECIES_COUNT):
        if any(R.species(sid).base_stats):
            out.append(sid)
    return out


def tm_label(item_id: int) -> str:
    n = item_id - R.ITEM_TM01
    if item_id <= 601:
        return f"TM{n + 1:03d}"
    return f"HM{item_id - 682 + 1:02d}"


def build(db: str) -> dict:
    con = sqlite3.connect(db)
    c = con.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS species; DROP TABLE IF EXISTS moves;
        DROP TABLE IF EXISTS type_chart; DROP TABLE IF EXISTS abilities;
        DROP TABLE IF EXISTS evolutions; DROP TABLE IF EXISTS learnset_levelup;
        DROP TABLE IF EXISTS tm_list; DROP TABLE IF EXISTS tm_compat;
        DROP TABLE IF EXISTS egg_moves; DROP TABLE IF EXISTS wild_levels;
        DROP TABLE IF EXISTS trainers;
        DROP TABLE IF EXISTS maps; DROP TABLE IF EXISTS map_connections;
        DROP TABLE IF EXISTS map_warps; DROP TABLE IF EXISTS map_objects;
        DROP TABLE IF EXISTS items; DROP TABLE IF EXISTS trainer_locations;
        DROP TABLE IF EXISTS wild_encounters; DROP TABLE IF EXISTS field_items;
        DROP TABLE IF EXISTS badge_flags; DROP TABLE IF EXISTS badge_gates;
        DROP TABLE IF EXISTS map_sections;
        CREATE TABLE species(id INTEGER PRIMARY KEY, name TEXT, hp INT, attack INT, defense INT,
            speed INT, sp_attack INT, sp_defense INT, type1 TEXT, type2 TEXT,
            catch_rate INT, exp_yield INT, ability1 TEXT, ability2 TEXT, hidden_ability TEXT);
        CREATE TABLE moves(id INTEGER PRIMARY KEY, name TEXT, type TEXT, power INT,
            accuracy INT, pp INT, priority INT, category TEXT, effect_id INT);
        CREATE TABLE type_chart(attack_type TEXT, defense_type TEXT, multiplier REAL);
        CREATE TABLE abilities(id INTEGER PRIMARY KEY, name TEXT, description TEXT);
        CREATE TABLE evolutions(species_id INT, method_id INT, param INT, target_species INT);
        CREATE TABLE learnset_levelup(species_id INT, level INT, move_id INT, move_name TEXT);
        CREATE TABLE tm_list(item_id INTEGER PRIMARY KEY, label TEXT, move_id INT, move_name TEXT);
        CREATE TABLE tm_compat(species_id INT, item_id INT);
        CREATE TABLE egg_moves(species_id INT, move_id INT, move_name TEXT);
        CREATE TABLE wild_levels("group" INT, num INT, min_level INT, max_level INT);
        CREATE TABLE trainers(name TEXT, kind TEXT, badges INT, slot INT,
            base_species INT, fielded_species INT, level INT);
        CREATE TABLE maps(grp INT, num INT, layout_id INT, music INT, mapsec INT, indoor INT,
            underwater INT, is_gym INT, is_center INT, is_mart INT, warp_count INT,
            conn_count INT, PRIMARY KEY(grp, num));
        CREATE TABLE map_connections(grp INT, num INT, direction INT, dest_group INT, dest_num INT);
        CREATE TABLE map_warps(grp INT, num INT, x INT, y INT, dest_group INT, dest_num INT);
        CREATE TABLE map_objects(grp INT, num INT, obj_id INT, x INT, y INT, movement INT,
            script_addr INT, flag INT);
        CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT, price INT);
        CREATE TABLE trainer_locations(trainer_id INT, name TEXT, grp INT, num INT, x INT, y INT);
        CREATE TABLE wild_encounters(grp INT, num INT, category INT, slot INT,
            min_level INT, max_level INT, species INT);
        CREATE TABLE field_items(grp INT, num INT, x INT, y INT, kind TEXT, item INT, flag INT);
        CREATE TABLE badge_flags(badge INT, flag INT, region TEXT, leader TEXT);
        CREATE TABLE badge_gates(grp INT, num INT, badge INT);
        CREATE TABLE map_sections(mapsec INTEGER PRIMARY KEY, name TEXT);
    """)
    n = {}
    species_ids = real_species()
    n["species"] = len(species_ids)
    # some ROWE form rows (id 1501+) carry a learnset pointer that passes the in-ROM check but
    # walks its terminator scan off the end; the base-stat/type/ability data still reads, so the
    # variable-length reads are guarded per species and the skips are reported, never hidden
    skipped = {"learnset_rows_skipped": 0, "tm_compat_skipped": 0, "egg_skipped": 0}
    for sid in species_ids:
        sp = R.species(sid)
        bs = sp.base_stats
        t1, t2 = sp.types
        a0, a1, ah = sp.abilities
        c.execute("INSERT INTO species VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            sid, R.species_name(sid), bs[R.HP], bs[R.ATK], bs[R.DEF], bs[R.SPE], bs[R.SPA], bs[R.SPD],
            TYPE[t1] if t1 < R.NUM_TYPES else t1, TYPE[t2] if t2 < R.NUM_TYPES else t2,
            sp.catch_rate, sp.exp_yield, ability(a0), ability(a1), ability(ah)))
        for method, param, target in R.evolutions(sid):
            c.execute("INSERT INTO evolutions VALUES (?,?,?,?)", (sid, method, param, target))
        try:
            learnset = R.level_up_learnset(sid)
        except (IndexError, struct.error):
            learnset, skipped["learnset_rows_skipped"] = (), skipped["learnset_rows_skipped"] + 1
        for level, mv in learnset:
            c.execute("INSERT INTO learnset_levelup VALUES (?,?,?,?)", (sid, level, mv, move_name(mv)))
        try:
            tms = sorted(R.tm_learnset(sid))
        except (IndexError, struct.error):
            tms, skipped["tm_compat_skipped"] = [], skipped["tm_compat_skipped"] + 1
        for item_id in tms:
            c.execute("INSERT INTO tm_compat VALUES (?,?)", (sid, item_id))
        try:
            eggs = R.egg_moves(sid)
        except (IndexError, struct.error):
            eggs, skipped["egg_skipped"] = (), skipped["egg_skipped"] + 1
        for mv in eggs:
            c.execute("INSERT INTO egg_moves VALUES (?,?,?)", (sid, mv, move_name(mv)))

    n["moves"] = 0
    for mid in range(1, R.MOVE_COUNT):
        m = R.move(mid)
        if not m.name.strip():
            continue
        c.execute("INSERT INTO moves VALUES (?,?,?,?,?,?,?,?,?)", (
            m.id, m.name, TYPE[m.type] if m.type < R.NUM_TYPES else m.type, m.power,
            m.accuracy, m.pp, m.priority, CATEGORY.get(m.split, m.split), m.effect))
        n["moves"] += 1

    chart = R.type_chart()
    for a in range(R.NUM_TYPES):
        for d in range(R.NUM_TYPES):
            c.execute("INSERT INTO type_chart VALUES (?,?,?)", (TYPE[a], TYPE[d], chart[a][d]))

    n["abilities"] = 0
    for aid in range(R.ABILITY_SCAN_CAP):
        name = R.ability_name(aid)
        if not name.strip():
            continue
        c.execute("INSERT INTO abilities VALUES (?,?,?)", (aid, name, R.ability_description(aid)))
        n["abilities"] += 1

    n["tm_list"] = 0
    for item_id in range(R.ITEM_TM01, R.ITEM_TM01 + R.TM_MOVES_COUNT):
        mv = R.tm_move(item_id)
        if not mv:
            continue
        c.execute("INSERT INTO tm_list VALUES (?,?,?,?)", (item_id, tm_label(item_id), mv, move_name(mv)))
        n["tm_list"] += 1

    wild = R.wild_land_levels()
    for (g, num), (lo, hi) in sorted(wild.items()):
        c.execute("INSERT INTO wild_levels VALUES (?,?,?,?)", (g, num, lo, hi))
    n["wild_levels"] = len(wild)

    roster = [(name, "gym", i) for i, name in enumerate(R.LEADERS)]
    roster += [(name, "league", R.LEAGUE_BADGES) for name in R.LEAGUE]
    for name, kind, badges in roster:
        base = R.leader_team(name, badges)
        built = R.leader_build(name, badges)
        for slot, ((bsp, lvl), (fsp, _)) in enumerate(zip(base, built)):
            c.execute("INSERT INTO trainers VALUES (?,?,?,?,?,?,?)", (name, kind, badges, slot, bsp, fsp, lvl))

    # the 8 Sevii leaders give badges 9-16; their levels scale at battle time, so level is null and
    # the raw ROM party species fill both base and fielded with no evolution projection
    for i, (name, pool) in enumerate(R.sevii_leader_pools()):
        for slot, sp in enumerate(pool):
            c.execute("INSERT INTO trainers VALUES (?,?,?,?,?,?,?)", (name, "sevii", 8 + i, slot, sp, sp, None))

    # every trainer's tile, recovered by walking map object scripts for each trainer id; the id
    # comes off the gTrainers base the Hoenn leaders' gym scripts confirm. The 8 Sevii leaders are
    # a subset, queryable by name
    for tid, name, grp, num, x, y in R.all_trainer_tiles():
        c.execute("INSERT INTO trainer_locations VALUES (?,?,?,?,?,?)", (tid, name, grp, num, x, y))

    gyms = R.gym_maps()
    n["maps"] = 0
    for g in range(R.MAP_GROUP_COUNT):
        for num in range(R.map_count(g)):
            if R.map_header(g, num) is None:
                continue
            conns = R.map_connections(g, num)
            warps = R.map_warps(g, num)
            c.execute("INSERT INTO maps VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                g, num, R.map_layout_id(g, num), R.map_music(g, num), R.map_section(g, num),
                int(R.is_indoor(g, num)), int(R.is_underwater(g, num)),
                int((g, num) in gyms), int(R.is_center(g, num)), int(R.is_mart(g, num)),
                len(warps), len(conns)))
            n["maps"] += 1
            for direction, (dg, dn) in conns:
                c.execute("INSERT INTO map_connections VALUES (?,?,?,?,?)", (g, num, direction, dg, dn))
            for x, y, (dg, dn) in warps:
                c.execute("INSERT INTO map_warps VALUES (?,?,?,?,?,?)", (g, num, x, y, dg, dn))
            # map_object_scripts and map_objects walk the same templates in order, so the flag
            # from the second pairs with the script addr from the first
            for (oid, ox, oy, mv, script), obj in zip(R.map_object_scripts(g, num), R.map_objects(g, num)):
                c.execute("INSERT INTO map_objects VALUES (?,?,?,?,?,?,?,?)",
                          (g, num, oid, ox, oy, mv, script, obj[3]))

    n["items"] = 0
    for item_id in range(1, R.ITEM_COUNT):
        name = R.item_name(item_id)
        if not name.strip():
            continue
        c.execute("INSERT INTO items VALUES (?,?,?)", (item_id, name, R.item_price(item_id)))
        n["items"] += 1

    for g, num, cat, slot, lo, hi, sp in R.wild_encounters():
        c.execute("INSERT INTO wild_encounters VALUES (?,?,?,?,?,?,?)", (g, num, cat, slot, lo, hi, sp))

    for g, num, x, y, kind, item, flag in R.field_items():
        c.execute("INSERT INTO field_items VALUES (?,?,?,?,?,?,?)", (g, num, x, y, kind, item, flag))

    for badge, flag, region, leader in R.badge_flags():
        c.execute("INSERT INTO badge_flags VALUES (?,?,?,?)", (badge, flag, region, leader))

    for g, num, badge in R.badge_gate_maps():
        c.execute("INSERT INTO badge_gates VALUES (?,?,?)", (g, num, badge))

    for mapsec, name in R.map_sections():
        c.execute("INSERT INTO map_sections VALUES (?,?)", (mapsec, name))

    con.commit()
    for t in ("evolutions", "learnset_levelup", "tm_compat", "egg_moves", "type_chart", "trainers",
              "map_connections", "map_warps", "map_objects", "trainer_locations",
              "wild_encounters", "field_items", "badge_flags", "badge_gates", "map_sections"):
        n[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    con.close()
    n.update(skipped)
    return n


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "/opt/brendbot/games/rowe/rowe_rom.db"
    n = build(out)
    print("wrote", out)
    for t, count in sorted(n.items()):
        print(f"  {t:18s} {count}")


if __name__ == "__main__":
    main()
