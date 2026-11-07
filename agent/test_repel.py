"""The travel-leg Repel. use_item_in_field uses a Repel from the Items pocket and sets
VAR_REPEL_STEP_COUNT in the save block, read back headless off lilycove.ss. maybe_repel fires one
only when the party out-levels the current map's wild max and none is active, so a walk past low
wilds pays no encounters."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "states", "fixtures", "lilycove.ss")
REPEL = 90
ROUTE_101 = (0, 16)  # wild land max 5


def test_use_item_in_field_sets_the_repel_step_count():
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test-repel.json")
    assert p.g.var(S.VAR_REPEL_STEP_COUNT) == 0
    held = dict(p.g.items()).get(REPEL)

    slot = next(i for i, (iid, _) in enumerate(p.g.items()) if iid == REPEL)
    assert p.errands.use_item_in_field(slot)

    assert p.g.var(S.VAR_REPEL_STEP_COUNT) == 100
    assert dict(p.g.items()).get(REPEL) == held - 1


class Mon:
    def __init__(self, level):
        self.level = level


class FakeErrands:
    def __init__(self, g):
        self.g, self.fired = g, False

    def use_item_in_field(self, slot):
        self.fired = True
        self.g._var = 100
        return True


class FakeG:
    def __init__(self, var, levels, repels):
        self._var, self._levels, self._repels = var, levels, repels

    def var(self, v):
        return self._var

    def position(self):
        return (5, 5, *ROUTE_101)

    def party(self):
        return [Mon(lv) for lv in self._levels]

    def repels(self):
        return self._repels

    def items(self):
        return [(REPEL, 5)]


def _player(var, levels, repels):
    p = play.Player.__new__(play.Player)
    p.g = FakeG(var, levels, repels)
    p.errands = FakeErrands(p.g)
    p.e = type("_E", (), {"read": lambda self, a, n=1: b"\x00"})()
    p.say = lambda s: None
    return p


def test_maybe_repel_fires_when_the_party_outlevels_the_wild_max():
    p = _player(0, [10, 12], [(REPEL, 5)])
    p.maybe_repel()
    assert p.errands.fired


def test_maybe_repel_skips_an_active_repel_and_an_under_leveled_party_and_an_empty_bag():
    active = _player(100, [10], [(REPEL, 5)])
    active.maybe_repel()
    assert not active.errands.fired

    under = _player(0, [5], [(REPEL, 5)])  # lead at the wild max, not above it
    under.maybe_repel()
    assert not under.errands.fired

    empty = _player(0, [10], [])
    empty.maybe_repel()
    assert not empty.errands.fired


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
