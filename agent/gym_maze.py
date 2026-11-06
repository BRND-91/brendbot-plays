"""A gym split across maps by warp pads (Eight Island's (2,15) over its annex (2,21), five pads
each way) is a graph of walkable pockets joined by the ROM warp table. gym_sweep spent each warp
once blind and ran out; the chain is a search instead."""
from collections import deque

import rowe_rom as R
from nav import Grid


def rom_grid(m: tuple) -> Grid:
    """A map's layout off the ROM w/ its object-event tiles blocked, for a map the player is not on."""
    w, h, cells = R.map_cells(*m)
    g = Grid.from_cells(w, h, cells)
    g._behavior = R.metatile_behavior(*m)
    g.blocked_by_npc = {(x, y) for x, y, *_ in R.map_objects(*m)}
    g.warp_tiles = {(x, y) for x, y, _ in R.map_warps(*m)}
    return g


def warp_chain(start: tuple, goal: tuple, maps: frozenset, grids: dict | None = None) -> list | None:
    """[(map, warp tile), ...] to step on in order from start=(map, tile) until goal=(map, tile) has
    a walking path; [] when it is walkable now, None when no chain inside `maps` reaches it. A grid
    in `grids` stands in for that map's ROM layout, so the live map carries its NPCs."""
    grids = dict(grids or {})
    links = {m: R.map_warp_links(*m) for m in maps}

    def grid(m: tuple) -> Grid:
        if m not in grids:
            grids[m] = rom_grid(m)
        return grids[m]

    prev = {start: None}
    q = deque([start])
    while q:
        node = q.popleft()
        m, t = node
        if m == goal[0] and (t == goal[1] or grid(m).path(t, goal[1]) is not None):
            chain = []
            while prev[node] is not None:
                node, tile = prev[node]
                chain.append((node[0], tile))
            return chain[::-1]
        for x, y, dest, dest_warp in links[m]:
            if dest not in maps or grid(m).path(t, (x, y)) is None:
                continue
            land = links[dest][dest_warp]
            nxt = (dest, (land[0], land[1]))
            if nxt in prev:
                continue
            prev[nxt] = (node, (x, y))
            q.append(nxt)
    return None
