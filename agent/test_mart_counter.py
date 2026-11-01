"""MART_COUNTER_TILE is walkable on LAYOUT_MART, no Mart posts a standing NPC on it, and the
clerk sits two tiles left of it across the counter end, so a LEFT press plus A talks through."""
import json
import struct
import sys

from routines import MART_COUNTER_TILE

SRC = "vendor/RoweSource/"
WANDER = "WANDER"


def _layout_collision(layout_id: str) -> tuple:
    lay = next(l for l in json.load(open(SRC + "data/layouts/layouts.json"))["layouts"] if l["id"] == layout_id)
    w, h = lay["width"], lay["height"]
    cells = struct.unpack(f"<{w * h}H", open(SRC + lay["blockdata_filepath"], "rb").read()[: w * h * 2])
    return w, h, [(c >> 10) & 3 for c in cells]


def blockers(tile: tuple) -> list:
    """Marts where `tile` is a wall, an NPC's fixed post, or not two right of the clerk."""
    x, y = tile
    groups = json.load(open(SRC + "data/maps/map_groups.json"))
    bad = []
    for g in groups["group_order"]:
        for name in groups[g]:
            if not name.endswith("_Mart"):
                continue
            m = json.load(open(f"{SRC}data/maps/{name}/map.json"))
            w, h, col = _layout_collision(m["layout"])
            if col[y * w + x]:
                bad.append((name, "wall"))
            objs = m["object_events"]
            if any(o["x"] == x and o["y"] == y and WANDER not in o["movement_type"] for o in objs):
                bad.append((name, "npc post"))
            clerks = [(o["x"], o["y"]) for o in objs if o["graphics_id"] == "OBJ_EVENT_GFX_MART_EMPLOYEE"]
            if (x - 2, y) not in clerks or not col[y * w + x - 1]:
                bad.append((name, "clerk not across the counter to the left"))
    return bad


def test_counter_tile_clear():
    assert blockers(MART_COUNTER_TILE) == []


if __name__ == "__main__":
    tile = tuple(int(v) for v in sys.argv[1:3]) if len(sys.argv) > 2 else MART_COUNTER_TILE
    print(tile, blockers(tile))
