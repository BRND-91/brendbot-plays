#!/usr/bin/env python3
"""Decode Rowe/Emerald event-script bytecode straight off the ROM.

The opcode -> argument-length table is generated from the decomp's macro source
(vendor/RoweSource/asm/macros/event.inc), not hand-maintained, so a 2.1b expansion
command that changes an arg layout changes the table the next run. A command macro is
one whose first emitted directive is a literal `.byte 0xNN`; that byte is the opcode and
the remaining emitted bytes are its args. Nested macro invocations in a body (warp's
`map` sub-macro) resolve their length against every macros/*.inc, so a nested emitter counts
for its real width. An opcode the table does not define is flagged, never guessed past.

CLI:
    script_decode.py 0x83078ed [0x83286de ...]   decode each script, follow call/goto targets
    script_decode.py --table                     dump the opcode table and exit
"""
import os
import re
import struct
import sys
from functools import lru_cache

import rowe_rom as R

MACRO_DIR = os.path.join(os.path.dirname(__file__), "vendor", "RoweSource", "asm", "macros")
_SIZE = {".byte": 1, ".2byte": 2, ".4byte": 4}
_HEX = re.compile(r"^0[xX][0-9a-fA-F]+$")

# opcodes after which a linear run stops: end, return, and the unconditional goto whose
# target is queued but whose fall-through is dead. gotostd (0x08) tail-jumps the same way.
_TERMINATORS = {0x02, 0x03, 0x05, 0x08}
# opcodes carrying a 4-byte script pointer as their last arg, to queue as a new block
_PTR_OPS = {0x04: 0, 0x05: 0, 0x06: 1, 0x07: 1}  # op -> byte offset of the 4-byte target

# trainerbattle (0x5C) is variable-length by its type byte, and the generated table cannot
# size it (the .if/.elseif chain has no .else branch to split on), so it is handled here.
# _TB_LEN is arg bytes per type; _TB_SCRIPT is the arg-byte offset of the one pointer that is
# an event script rather than battle text, which is where a gym leader sets its badge flag.
_TRAINERBATTLE = 0x5C
_TB_LEN = {0: 13, 1: 17, 2: 17, 3: 9, 4: 17, 5: 13, 6: 21, 7: 17, 8: 21, 9: 13, 10: 13, 11: 13, 12: 13}
_TB_SCRIPT = {1: 13, 2: 13, 6: 17, 8: 17}


def _macros(path: str) -> dict:
    """name -> list of body lines (comments and .endm stripped) for one .inc file."""
    out, name, body = {}, None, []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.split("@", 1)[0].strip()
        if line.startswith(".macro "):
            name = line[len(".macro "):].split()[0].split(",")[0]
            body = []
        elif line == ".endm":
            if name is not None:
                out[name] = body
            name = None
        elif name is not None and line:
            body.append(line)
    return out


def _all_macros() -> dict:
    """Every macro across macros/*.inc, for resolving a nested invocation's width. event.inc
    owns the opcode table; the rest are here only so a body like `map` sub-macro has a length."""
    merged = {}
    for fn in sorted(os.listdir(MACRO_DIR)):
        if fn.endswith(".inc"):
            merged.update(_macros(os.path.join(MACRO_DIR, fn)))
    return merged


def _body_len(body: list, allm: dict, seen: frozenset) -> int:
    total = 0
    for ln in body:
        tok = ln.split()
        head = tok[0]
        if head in _SIZE:
            total += _SIZE[head]
        elif head in allm and head not in seen:
            total += _body_len(allm[head], allm, seen | {head})
    return total


def _variants(body: list) -> list:
    """Flatten a macro body's `.ifb`/`.ifnb`/`.if` conditional into one flat body per branch.
    applymovement et al. emit a different opcode with and without their optional `map` arg
    (0x4F vs 0x50), so the no-map and with-map forms are both real commands in the stream."""
    for i, ln in enumerate(body):
        head = ln.split()[0] if ln.split() else ""
        if head in (".ifb", ".ifnb", ".if"):
            depth, else_i, end_i = 0, None, None
            for j in range(i, len(body)):
                hj = body[j].split()[0] if body[j].split() else ""
                if hj in (".ifb", ".ifnb", ".if"):
                    depth += 1
                elif hj == ".else" and depth == 1:
                    else_i = j
                elif hj == ".endif":
                    depth -= 1
                    if depth == 0:
                        end_i = j
                        break
            if end_i is None:
                break
            pre, post = body[:i], body[end_i + 1:]
            if_b = body[i + 1:else_i] if else_i is not None else body[i + 1:end_i]
            else_b = body[else_i + 1:end_i] if else_i is not None else []
            out = []
            for branch in (if_b, else_b):
                out.extend(_variants(pre + branch + post))
            return out
    return [body]


def build_table() -> tuple:
    """(opcode -> (name, arg_len), name -> opcode). A command macro's first emitted directive is
    a literal `.byte 0xNN`; composite macros (giveitem, msgbox) emit no opcode and are skipped,
    since the simple opcodes their expansion emits already carry the stream. setdefault keeps the
    first/simplest form of a shared opcode."""
    allm = _all_macros()
    event = _macros(os.path.join(MACRO_DIR, "event.inc"))
    table, names = {}, {}
    for name, body in event.items():
        for variant in _variants(body):
            if not variant:
                continue
            tok = variant[0].split()
            if tok[0] != ".byte" or len(tok) < 2 or not _HEX.match(tok[1]):
                continue  # composite or non-command macro form
            op = int(tok[1], 16)
            arg_len = _body_len(variant, allm, frozenset()) - 1
            if arg_len < 0:
                continue
            table.setdefault(op, (name, arg_len))
            names.setdefault(name, op)
    return table, names


TABLE, NAMES = build_table()


def _u8(fo: int) -> int:
    return R._rom()[fo]


def _u16(fo: int) -> int:
    return struct.unpack_from("<H", R._rom(), fo)[0]


def _u32(fo: int) -> int:
    return struct.unpack_from("<I", R._rom(), fo)[0]


def _fmt_args(name: str, op: int, fo: int, arg_len: int) -> str:
    """Interpret the arg bytes for the commands that gate a Sevii warp. Everything else
    renders as raw hex so a reader can still see the operand without a per-op formatter."""
    if name in ("setflag", "clearflag", "checkflag"):
        return f"flag=0x{_u16(fo):X}"
    if name == "checkitem":
        return f"item=0x{_u16(fo):X} qty={_u16(fo + 2)}"
    if name in ("additem", "removeitem"):
        return f"item=0x{_u16(fo):X} qty={_u16(fo + 2)}"
    if name in ("goto", "call"):
        return f"-> 0x{_u32(fo):08X}"
    if name in ("goto_if", "call_if"):
        return f"cond={_u8(fo)} -> 0x{_u32(fo + 1):08X}"
    if name == "compare":
        return f"var=0x{_u16(fo):X} val=0x{_u16(fo + 2):X}"
    if name in ("setvar", "addvar", "copyvar", "setorcopyvar"):
        return f"var=0x{_u16(fo):X} val=0x{_u16(fo + 2):X}"
    if name in ("gotostd", "callstd"):
        return f"std={_u8(fo)}"
    if name == "warp" or name.startswith("warp") or name in ("setwarp", "setdivewarp", "setholewarp"):
        g, n = _u8(fo), _u8(fo + 1)
        return f"map=({g},{n}) warp={_u8(fo + 2)} x={_u16(fo + 3)} y={_u16(fo + 5)}"
    if name == "special":
        return f"special=0x{_u16(fo):X}"
    raw = R._rom()[fo:fo + arg_len].hex()
    return f"args={raw}" if raw else ""


def decode(addr: int, _blocks=None, _depth=0) -> list:
    """Walk from a ROM address, following call/goto/goto_if/call_if targets, until every
    reachable block ends on a terminator or an unknown opcode. Returns formatted lines."""
    blocks = {} if _blocks is None else _blocks
    worklist = [addr]
    out = []
    while worklist:
        start = worklist.pop(0)
        if start in blocks or not R._in_rom(start):
            continue
        blocks[start] = True
        out.append(f"--- block 0x{start:08X} ---")
        fo = R._fo(start)
        while True:
            op = _u8(fo)
            ea = start + (fo - R._fo(start))
            if op == _TRAINERBATTLE:
                typ = _u8(fo + 1)
                al = _TB_LEN.get(typ)
                if al is None:
                    out.append(f"0x{ea:08X}: trainerbattle    0x5C  UNKNOWN type {typ}, stopping block")
                    break
                so = _TB_SCRIPT.get(typ)
                tgt = _u32(fo + 1 + so) if so is not None else None
                tail = f" event_script -> 0x{tgt:08X}" if tgt is not None else ""
                out.append(f"0x{ea:08X}: trainerbattle    0x5C  type={typ} trainer=0x{_u16(fo + 2):X}{tail}")
                if tgt is not None and R._in_rom(tgt):
                    worklist.append(tgt)
                fo += 1 + al
                continue
            if op not in TABLE:
                out.append(f"0x{ea:08X}: UNKNOWN opcode 0x{op:02X}  <-- table miss, stopping block")
                break
            name, arg_len = TABLE[op]
            argfo = fo + 1
            out.append(f"0x{ea:08X}: {name:<16} 0x{op:02X}  {_fmt_args(name, op, argfo, arg_len)}")
            if op in _PTR_OPS:
                tgt = _u32(argfo + _PTR_OPS[op])
                if R._in_rom(tgt):
                    worklist.append(tgt)
            fo += 1 + arg_len
            if op in _TERMINATORS:
                break
    return out


_WARP_LINE = re.compile(r"^0x([0-9A-F]{8}): (\S+)\s+0x([0-9A-F]{2})")


def _entry_scripts(g: int, n: int) -> list:
    """ROM addresses of every script hung off map (g,n)'s object, coord, bg, and map-script events.
    A var-conditional map-script table (types 2 and 4) is a list of {var, value, script}, so its
    script pointers are read from offset 4 of each row rather than taken as a script themselves."""
    h = R.map_header(g, n)
    if h is None:
        return []
    rom = R._rom()
    out = []
    ev = _u32(h + R.MAPHDR_EVENTS)
    if R._in_rom(ev):
        efo = R._fo(ev)
        nobj, ncoord, nbg = rom[efo], rom[efo + 2], rom[efo + 3]
        pobj, pcoord, pbg = _u32(efo + 4), _u32(efo + 12), _u32(efo + 16)
        if nobj and R._in_rom(pobj) and R._in_rom(pobj + nobj * R.OBJ_STRIDE):
            out += [_u32(R._fo(pobj) + i * R.OBJ_STRIDE + 0x10) for i in range(nobj)]
        if ncoord and R._in_rom(pcoord) and R._in_rom(pcoord + ncoord * 16):
            out += [_u32(R._fo(pcoord) + i * 16 + 12) for i in range(ncoord)]
        if nbg and R._in_rom(pbg) and R._in_rom(pbg + nbg * 12):
            out += [_u32(R._fo(pbg) + i * 12 + 8) for i in range(nbg) if rom[R._fo(pbg) + i * 12 + 5] < 5]
    msc = _u32(h + R.MAPHDR_SCRIPTS)
    if R._in_rom(msc):
        o = R._fo(msc)
        for _ in range(32):
            if rom[o] == 0:
                break
            t, sptr = rom[o], _u32(o + 1)
            o += 5
            if t in (2, 4) and R._in_rom(sptr):
                w = R._fo(sptr)
                for _ in range(64):
                    if _u16(w) == 0:
                        break
                    out.append(_u32(w + 4))
                    w += 8
            else:
                out.append(sptr)
    return [a for a in out if R._in_rom(a)]


_GOTO, _CALL, _GOTO_IF, _CALL_IF = 0x05, 0x04, 0x06, 0x07


def _warp_paths(addr: int, _budget: int = 80000) -> list:
    """(dest_map, warp_id, gate) for every warp reachable from addr, gate being the frozenset of flags
    that must be SET along the control-flow path that reaches that warp. A conditional branch splits
    into its taken and fall-through paths, each carrying its own flag requirement, so a branch-local
    checkflag gates only the warps on that branch (the progressive island unlocks) and not every warp
    that happens to follow a checkflag in block order. A moving warp (name warp*) ends its path; a
    setwarp records its target and keeps walking, since it transfers nothing. A path that needs the
    same flag both set and unset is dead and dropped. Loops are cut by a visited (offset, required)
    set; the budget bounds a pathological nest."""
    rom = R._rom()
    n = len(rom)
    out, seen, steps = [], set(), 0
    stack = [(R._fo(addr), frozenset(), frozenset(), None)]  # offset, required, forbidden, pending flag
    while stack and steps < _budget:
        fo, req, forb, flag = stack.pop()
        while steps < _budget:
            steps += 1
            if fo < 0 or fo + 1 > n or (fo, req) in seen:
                break
            seen.add((fo, req))
            op = rom[fo]
            if op == _TRAINERBATTLE:
                al = _TB_LEN.get(rom[fo + 1])
                if al is None:
                    break
                fo, flag = fo + 1 + al, None
                continue
            if op not in TABLE:
                break
            name, arg_len = TABLE[op]
            argfo = fo + 1
            if name == "checkflag":
                flag = _u16(argfo)
            elif name == "compare_var_to_value":
                flag = None
            elif op in (_GOTO_IF, _CALL_IF):
                cond, tgt = rom[argfo], _u32(argfo + 1)
                if flag is not None and cond in (0, 1):
                    on_set = cond == 1  # goto_if_set takes the branch when the flag is set
                    t_req = req | ({flag} if on_set else frozenset())
                    t_forb = forb | (frozenset() if on_set else {flag})
                    f_req = req | (frozenset() if on_set else {flag})
                    f_forb = forb | ({flag} if on_set else frozenset())
                else:
                    t_req, t_forb, f_req, f_forb = req, forb, req, forb
                if R._in_rom(tgt) and not (t_req & t_forb):
                    stack.append((R._fo(tgt), frozenset(t_req), frozenset(t_forb), None))
                if f_req & f_forb:
                    break
                req, forb, flag = frozenset(f_req), frozenset(f_forb), None
                fo = argfo + arg_len
                continue
            elif op == _GOTO:
                tgt = _u32(argfo)
                if not R._in_rom(tgt):
                    break
                fo, flag = R._fo(tgt), None
                continue
            elif op == _CALL:
                tgt = _u32(argfo)
                if R._in_rom(tgt):
                    stack.append((R._fo(tgt), req, forb, None))
                fo, flag = argfo + arg_len, None
                continue
            elif "warp" in name:
                out.append(((rom[argfo], rom[argfo + 1]), rom[argfo + 2], req))
                if name.startswith("warp"):
                    break
                fo, flag = argfo + arg_len, None
                continue
            if op in _TERMINATORS:
                break
            fo = argfo + arg_len
    return out


def _script_warps(addr: int) -> list:
    """(dest_map, gate) per warp reachable from addr, keeping the least-restrictive gate per dest.
    Gate is the flags required set on the control-flow path to the warp (see _warp_paths)."""
    best = {}
    for dest, _wid, gate in _warp_paths(addr):
        if dest not in best or len(gate) < len(best[dest]):
            best[dest] = gate
    return list(best.items())


@lru_cache(maxsize=1)
def script_edges() -> dict:
    """{(group,num): {(dest_group,dest_num): frozenset(gate_flag_ids)}} for every event script that
    reaches a warp command. The least-restrictive gate is kept when a destination has more than one
    path. These are the NPC-interaction crossings (the Seagallop ferry) that world_edges misses,
    since it reads only the connection and warp-event tables, never a script's warp command."""
    out = {}
    for g in range(R.MAP_GROUP_COUNT):
        for n in range(R.map_count(g)):
            dests = out.setdefault((g, n), {})
            for addr in _entry_scripts(g, n):
                for dest, gate in _script_warps(addr):
                    if dest not in dests or len(gate) < len(dests[dest]):
                        dests[dest] = gate
    return {src: d for src, d in out.items() if d}


@lru_cache(maxsize=1)
def gate_flags() -> frozenset:
    """Every flag id that gates at least one script edge, so a live run reads just these from the
    emulator to decide which NPC-interaction crossings are open this frame."""
    return frozenset(f for d in script_edges().values() for gate in d.values() for f in gate)


def talk_object(src: tuple, dest: tuple) -> dict | None:
    """The object on map src whose A-press script reaches a warp to dest, with the tile to stand on
    and the direction to face it. None when no object's script warps there. The approach is the tile
    below the object facing up, the side a dock sailor is read from; an object that can only be faced
    from another side would need its movement type consulted, which the dock does not."""
    for idx, x, y, mv, addr in R.map_object_scripts(src[0], src[1]):
        if not R._in_rom(addr):
            continue
        if any(d == dest for d, _wid, _gate in _warp_paths(addr)):
            return {"index": idx, "obj": (x, y), "approach": (x, y + 1),
                    "facing": (0, -1), "movement": mv, "script": addr}
    return None


# The Seagallop sailor opens a native ScrollingMultichoice the bytecode walker can't read, so which
# menu row warps where is not decodable the way menu_sequence resolves a yes/no chain. The rows the
# menu lists (Slateport City, then One..Eight Island) map to the ferry's ungated warp arms in
# ascending map order; (9,9) Slateport City and (0,79) Three Island are land-verified on the (13,10)
# fixture. talk_warp matches these labels against the live option array.
SEAGALLOP_DOCKS = frozenset({(9, 9), (13, 10)})
_SEAGALLOP_LABELS = {
    (9, 9): "Slateport City",
    (0, 75): "One Island",
    (0, 76): "Two Island",
    (0, 79): "Three Island",
    (0, 123): "Four Island",
    (1, 32): "Five Island",
    (1, 58): "Six Island",
    (1, 66): "Seven Island",
    (2, 14): "Eight Island",
}


def seagallop_label(src: tuple, dest: tuple) -> str | None:
    """The menu row text that warps the Seagallop sailor on dock `src` to `dest`, or None when the
    crossing is not a Seagallop talk (a normal script warp the walker drives through take_warp)."""
    if src not in SEAGALLOP_DOCKS:
        return None
    return _SEAGALLOP_LABELS.get(dest)


_MENU_OPS = {0x6F: "multi", 0x70: "multi", 0x71: "multi", 0x6E: "yesno"}
_RESULT_VAR = 0x800D   # VAR_RESULT, where a menu writes the chosen index
_CANCEL = 0x7F         # the B-press case a multichoice switch tests last


def _pick_paths(addr: int, _budget: int = 400000) -> list:
    """(dest_map, picks) for every warp reachable from addr, picks the ordered menu choices the path
    takes to reach it, fewest-picks first per destination. A menu op (multichoice/yesnobox) writes
    VAR_RESULT; the `switch` macro copies that into a scratch var and each `case` compares it, so the
    live result is tracked through copyvar/setorcopyvar rather than one fixed var. A `goto_if` equal
    on a var currently holding the menu result records (menu_type, value) and consumes that menu, so
    the next menu op starts fresh. The B-cancel value 0x7F is pruned. A compare on VAR_RESULT before
    any menu is a precondition a special set, so its branch is followed without recording a pick.

    A menu case sets a constant dispatch code with `setvar` and a shared tail compares it to pick the
    warp, so the state propagates known constants too: a `goto_if` on a constant-valued var follows
    only the branch that constant takes, which keeps each menu-pick prefix landing on one warp instead
    of every dispatch arm. The search is over script states (fo, menu, result-vars, pending-compare,
    constants), not pick prefixes, since a state's reachable warps do not depend on how it was reached.
    A 0-1 traversal pops fewest-picks first and finalizes each state once, so every warp is reached
    with its shortest chain and a cancel-reprompt loop cannot grow an unbounded prefix."""
    import heapq
    rom = R._rom()
    n = len(rom)
    out, best, steps, tie = [], set(), 0, 0
    start = (R._fo(addr), None, frozenset(), None, frozenset())  # fo, menu, rvars, cmp, consts
    heap = [(0, 0, start, ())]  # picks_len, tie, state, picks
    while heap and steps < _budget:
        steps += 1
        _, _, state, picks = heapq.heappop(heap)
        if state in best:
            continue
        best.add(state)
        fo, menu, rvars, cmp, consts = state
        if fo < 0 or fo + 1 > n:
            continue
        op = rom[fo]
        succ = []  # (next_fo, menu, rvars, cmp, consts, picks)
        if op == _TRAINERBATTLE:
            al = _TB_LEN.get(rom[fo + 1])
            if al is not None:
                succ.append((fo + 1 + al, menu, rvars, None, consts, picks))
        elif op in TABLE:
            name, arg_len = TABLE[op]
            argfo = fo + 1
            nxt = argfo + arg_len
            cvals = dict(consts)
            if op in _MENU_OPS:
                succ.append((nxt, _MENU_OPS[op], frozenset({_RESULT_VAR}),
                             None, _without(consts, _RESULT_VAR), picks))
            elif name in ("copyvar", "setorcopyvar"):
                dst, src = _u16(argfo), _u16(argfo + 2)
                nrv = rvars | {dst} if src in rvars else rvars - {dst}
                ncs = _without(consts, dst) | ({(dst, cvals[src])} if src in cvals else frozenset())
                succ.append((nxt, menu, nrv, None, ncs, picks))
            elif name == "setvar":
                dst = _u16(argfo)
                succ.append((nxt, menu, rvars - {dst}, None,
                             _without(consts, dst) | {(dst, _u16(argfo + 2))}, picks))
            elif name == "addvar":
                dst = _u16(argfo)
                succ.append((nxt, menu, rvars - {dst}, None, _without(consts, dst), picks))
            elif name == "compare_var_to_value":
                succ.append((nxt, menu, rvars, (_u16(argfo), _u16(argfo + 2)), consts, picks))
            elif op in (_GOTO_IF, _CALL_IF):
                cond, tgt = rom[argfo], _u32(argfo + 1)
                var, val = cmp if cmp else (None, None)
                take_tgt = take_fall = True
                pick = None
                if cmp and var in cvals:  # constant dispatch: one arm is live
                    if (cvals[var] == val) == (cond == 1):
                        take_fall = False
                    else:
                        take_tgt = False
                elif cmp and var in rvars and cond == 1:  # a menu result branch
                    if val == _CANCEL:
                        take_tgt = False
                    elif menu is not None:
                        pick = (menu, val)
                if take_tgt and R._in_rom(tgt):
                    if pick is not None:
                        succ.append((R._fo(tgt), None, frozenset(), None, consts, picks + (pick,)))
                    else:
                        succ.append((R._fo(tgt), menu, rvars, None, consts, picks))
                if take_fall:
                    succ.append((nxt, menu, rvars, None, consts, picks))
            elif op == _GOTO:
                tgt = _u32(argfo)
                if R._in_rom(tgt):
                    succ.append((R._fo(tgt), menu, rvars, None, consts, picks))
            elif op == _CALL:
                tgt = _u32(argfo)
                if R._in_rom(tgt):
                    succ.append((R._fo(tgt), menu, rvars, None, consts, picks))
                succ.append((nxt, menu, rvars, None, consts, picks))
            elif "warp" in name:
                out.append(((rom[argfo], rom[argfo + 1]), picks))
                if not name.startswith("warp"):
                    succ.append((nxt, menu, rvars, None, consts, picks))
            elif op not in _TERMINATORS:
                succ.append((nxt, menu, rvars, None, consts, picks))
        for nfo, nmenu, nrvars, ncmp, nconsts, npicks in succ:
            ns = (nfo, nmenu, nrvars, ncmp, nconsts)
            if ns not in best:
                tie += 1
                heapq.heappush(heap, (len(npicks), tie, ns, npicks))
    return out


def _without(consts: frozenset, var: int) -> frozenset:
    return frozenset(p for p in consts if p[0] != var)


def menu_sequence(src: tuple, dest: tuple) -> tuple | None:
    """The shortest sequence of menu picks that drives the NPC on map src to warp to dest, each pick
    a (kind, value) pair with kind "multi" (move the cursor to index value) or "yesno" (value 1 is
    A on yes, 0 is B on no). None when no object there warps to dest. The executor feeds this to the
    dock menu; a run-time precondition that selects which sub-menu is live (a special sets VAR_RESULT
    before the first menu) is resolved on the dock itself, so this is the pick tail past that point."""
    t = talk_object(src, dest)
    if t is None:
        return None
    best = None
    for d, picks in _pick_paths(t["script"]):
        if d == dest and (best is None or len(picks) < len(best)):
            best = picks
    return best


def main() -> None:
    if "--table" in sys.argv:
        print(f"{len(TABLE)} opcodes parsed from event.inc")
        for op in sorted(TABLE):
            name, al = TABLE[op]
            print(f"  0x{op:02X} {name:<20} arg_len={al}")
        return
    for a in sys.argv[1:]:
        addr = int(a, 16)
        print(f"==== decode 0x{addr:08X} ====")
        for ln in decode(addr):
            print(ln)
        print()


if __name__ == "__main__":
    main()
