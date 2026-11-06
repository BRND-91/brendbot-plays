"""After the game clear, walking into Birch's lab (1,4) starts the National Dex scene, a lockall
w/ text, and the live walker missed into the lab on its way south and could not step back out:
'travel stuck: stuck (1, 4) -> [0, 9] 5x from (6, 5)'. scene_step presses A through it while
VAR_DEX_UPGRADE_JOHTO_STARTER_STATE reads a running scene, after which the door is walkable.
states/fixtures/littleroot_bedroom.ss is the post-credits bedroom w/ its flash file beside it."""
import os
import shutil

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "littleroot_bedroom.ss")
HOUSE_1F = (1, 0)
TOWN = (0, 9)


def test_lab_scene_runs_on_a_and_the_door_opens_after():
    work = "/tmp/rowe-birch-lab.ss"
    sav = "/tmp/rowe-birch-lab.sav"
    shutil.copy(FIXTURE, work)
    shutil.copy(FIXTURE[:-3] + ".sav", sav)
    e = eb.Emu(save=sav)
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=work + ".json")
    p.goal = {"mode": "travel", "to": [24, 107]}
    assert p.g.var(play.VAR_JOHTO_STARTER) == 1
    for dest in (HOUSE_1F, TOWN, play.BIRCH_LAB):
        r = p.errands.take_warp(dest)
        assert r == "map_changed", f"warp to {dest} -> {r} at {p.g.position()}"
    assert p.g.position()[2:] == play.BIRCH_LAB
    ticks = 0
    while ticks < 200 and (p.cutscene_step() or p.scene_step(play.BIRCH_LAB)):
        ticks += 1
    assert ticks < 200, f"the lab scene never ended: var {p.g.var(play.VAR_JOHTO_STARTER)} at {p.g.position()}"
    assert p.g.var(play.VAR_JOHTO_STARTER) not in play.LAB_SCENE_STATES
    assert p.scene_step(play.BIRCH_LAB) is False
    r = p.errands.take_warp(TOWN)
    assert r == "map_changed", f"door out after the scene -> {r} at {p.g.position()}"
    assert p.g.position()[2:] == TOWN
