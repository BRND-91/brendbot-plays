"""The gym goal carries the leader's stand read off the ROM's object scripts. On Bugsy's gym (2,8)
the entry-time heuristic (northmost static object) picked gym trainer Al at (0,7), so the run fought
Al, re-read his beaten dialog as "talked" and closed the gym five times a run (states/grind.log
"gym: leader -> talked at (0, 8) stand (0, 8)"). Bugsy's object sits at (6,13)."""
import planner

BUGSY_GYM, FALKNER_GYM, ROXANNE_GYM = (2, 8), (2, 7), (11, 3)


def test_bugsy_stand_is_below_his_object_not_the_northmost_trainer():
    assert planner.leader_stand(BUGSY_GYM) == (6, 14)


def test_falkner_stand_matches_the_gym_the_heuristic_cleared():
    # control: Falkner at (4,2) is also the northmost object, and that gym was beaten on the heuristic
    assert planner.leader_stand(FALKNER_GYM) == (4, 3)


def test_roxanne_stand_matches_the_hand_seeded_table():
    assert planner.leader_stand(ROXANNE_GYM) == planner.GYM_STAND[ROXANNE_GYM]


def test_sevii_gym_goal_carries_the_stand():
    class _Graph:
        visited = set()
        gated = {}

        def route(self, src, dst, blocked=frozenset(), field_moves=frozenset()):
            return dst

    status = {"map": [0, 76], "badges": 9, "badge_flags": [True] * 8,
              "johto_flags": [True] + [False] * 7, "party": [], "field_moves": []}
    goal, _why = planner.sevii_goal(_Graph(), frozenset(), status)
    assert goal["map"] == [2, 8] and goal["stand"] == [6, 14], goal
