"""Eight Island's gym (2,15) and its annex (2,21) off the ROM: from the door the stand (5,4) is two
pads away, (1,10) down to the annex and (8,10) back up to the (9,10) pocket the stand is walkable
from. Landings measured on a copy of the live save: the annex pad (8,10) fires 20 frames after
the step lands and puts the player on (9,10) of (2,15)."""
import gym_maze
import play

GYM, ANNEX = (2, 15), (2, 21)


def test_annex_is_inside_the_gym_map_set():
    assert ANNEX in play.gym_map_set(GYM)
MAPS = frozenset({GYM, ANNEX})
STAND = (5, 4)


def test_chain_from_the_door_to_the_stand():
    assert gym_maze.warp_chain((GYM, (4, 20)), (GYM, STAND), MAPS) == [(GYM, (1, 10)), (ANNEX, (8, 10))]


def test_walkable_goal_needs_no_warp():
    assert gym_maze.warp_chain((GYM, (9, 10)), (GYM, STAND), MAPS) == []


def test_annex_landing_is_one_pad_from_the_stand():
    assert gym_maze.warp_chain((ANNEX, (1, 10)), (GYM, STAND), MAPS) == [(ANNEX, (8, 10))]
