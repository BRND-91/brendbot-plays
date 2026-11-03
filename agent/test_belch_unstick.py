"""Belch is barred until its holder's berry is gone, so a mon that scores Belch highest without
having eaten a berry picks another move instead of wedging the action menu on a move the engine
refuses. Fixture states/fixtures/belch_stall.ss is the wild Eiscue fight that froze the live grind:
Greedent holds an item (berry unconsumed) and scored Belch top."""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_rom as R  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states", "fixtures", "belch_stall.ss")


def _player():
    e = eb.Emu()
    with open(FIXTURE, "rb") as f:
        e.load_state(f.read())
    return play.Player(e, play.NullStreamer())


def _belch_slot(me):
    return next(i for i, mv in enumerate(me.moves) if R.move(mv).name.lower() == "belch")


def main() -> None:
    p = _player()
    _, me, foes = p.sides()
    belch = _belch_slot(me)
    assert me.item != 0, "fixture should hold an item with the berry unconsumed"
    assert foes, "fixture should have a live foe"

    # control for BM_ITEM=0x30, the offset the guard reads. Anchor it against the party struct's
    # max HP: battle max_hp is read at 0x2E, so when it equals the party authority the field after
    # it (0x30) is the held item, which rules out the vanilla expansion's item-at-0x2E layout.
    pm = p.g.party()[p.g.battler_slot(me.battler)]
    assert me.max_hp == pm.max_hp, f"0x2E unanchored: battle max_hp {me.max_hp} != party {pm.max_hp}"
    assert R.item_name(me.item), f"item at 0x30 did not resolve to a real item: {me.item}"
    assert all(f.item == 0 for f in foes), "a no-item foe read nonzero at 0x30"

    # item still held, berry unconsumed: Belch is barred and pick_move takes a move with PP instead
    assert p._selectable(me, R.move(me.moves[belch])) is False, "Belch selectable with its item still held"
    pick = p.pick_move(me, foes)
    assert pick != belch, f"Belch (slot {belch}) picked while its berry is unconsumed"
    assert me.moves[pick] and me.pp[pick], "fell to an empty or spent slot"

    # held at the first action, gone now: the eaten-berry precondition holds and Belch is the top pick
    p2 = _player()
    _, me2raw, foes2 = p2.sides()
    me2 = replace(me2raw, item=0)
    p2._start_items[me2.personality] = me.item
    assert p2._selectable(me2, R.move(me2.moves[belch])) is True, "Belch still barred after its berry is gone"
    assert p2.pick_move(me2, foes2) == belch, "Belch not selected once the berry is consumed"

    # a berryless mon that switches into a slot whose prior occupant held an item must not inherit
    # that baseline: the eaten-berry guard tracks the mon that acted, not the slot. Greedent comes
    # in holding nothing (item 0) over a slot carrying a prior nonzero baseline, Belch stays barred.
    p4 = _player()
    _, me4raw, foes4 = p4.sides()
    me4 = replace(me4raw, item=0)
    p4._start_items[me4.battler] = me.item  # the slot's prior occupant, not this mon
    assert me4.personality not in p4._start_items, "test needs the switched-in mon absent from the baseline"
    assert p4._selectable(me4, R.move(me4.moves[belch])) is False, "Belch enabled off a prior slot occupant's baseline"
    assert p4.pick_move(me4, foes4) != belch, "Belch picked for a berryless switch-in"

    # with Belch barred the frozen grind acts: the battle leaves its stuck signature
    p3 = _player()
    sig0 = p3.battle_signature()
    advanced = False
    for _ in range(60):
        p3.battle_step()
        if not p3.g.in_battle() or p3.battle_signature() != sig0:
            advanced = True
            break
    assert advanced, "battle never left its frozen signature"
    print("ok")


if __name__ == "__main__":
    main()
