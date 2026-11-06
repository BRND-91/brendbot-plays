"""Move effects the damage formula has to know about. Last Resort fails until every other move has
been used this battle, and the chooser picked it 319 times off its 140 power as Stoutland's opener.
A recharge or charge move (Giga Impact, Solar Beam) spends two turns per hit, so it scores at half.
Future Sight lands two turns on and fails while one is pending, so it never outranks a direct hit.
A bench mon w/ a one-hit super-effective KO comes in over an active that needs three hits, even when
the active is not losing the exchange."""
from battle_engine import best_switch, rank_moves
from rowe_state import BattleMon, PartyMon

LAST_RESORT, GIGA_IMPACT, TAKE_DOWN, FUTURE_SIGHT, TACKLE, THUNDERBOLT, WATER_GUN = 387, 416, 36, 248, 33, 85, 55
NORMAL, ELECTRIC, WATER, MYSTERY = 0, 13, 11, 9
STOUTLAND, PAWMOT, SEAKING = 508, 923, 119


def _mon(moves, pp, types, **kw) -> BattleMon:
    base = dict(battler=0, species=STOUTLAND, level=50, hp=150, max_hp=150, ability=0, status1=0,
                stat_stages=(6,) * 8, nickname="x", personality=1, atk=100, dfn=80, spd=80, sp_atk=60, sp_def=80)
    base.update(kw)
    return BattleMon(moves=moves, pp=pp, types=types, **base)


def _foe(**kw) -> BattleMon:
    return _mon((TACKLE, 0, 0, 0), (35, 0, 0, 0), (NORMAL, NORMAL, MYSTERY), battler=1, species=SEAKING,
                personality=2, **kw)


def _scores(user, foe, used=frozenset()) -> dict:
    return {s.move.id: s.score for s in rank_moves(user, foe, used)}


def test_last_resort_scores_zero_until_the_other_moves_are_used():
    me = _mon((LAST_RESORT, TAKE_DOWN, TACKLE, 0), (5, 20, 35, 0), (NORMAL, NORMAL, MYSTERY))
    fresh = _scores(me, _foe())
    assert fresh[LAST_RESORT] == 0 and fresh[TAKE_DOWN] > 0
    spent = _scores(me, _foe(), used=frozenset({1, 2}))
    assert spent[LAST_RESORT] > spent[TAKE_DOWN]


def test_recharge_move_scores_half_so_take_down_outranks_giga_impact():
    me = _mon((GIGA_IMPACT, TAKE_DOWN, 0, 0), (5, 20, 0, 0), (NORMAL, NORMAL, MYSTERY))
    s = _scores(me, _foe())
    assert s[TAKE_DOWN] > s[GIGA_IMPACT] > 0


def test_future_sight_scores_zero():
    me = _mon((FUTURE_SIGHT, TACKLE, 0, 0), (10, 35, 0, 0), (WATER, WATER, MYSTERY), species=55)
    assert _scores(me, _foe())[FUTURE_SIGHT] == 0


def test_bench_with_a_one_hit_super_effective_ko_comes_in():
    active = _mon((TACKLE, 0, 0, 0), (35, 0, 0, 0), (NORMAL, NORMAL, MYSTERY), level=30, hp=60, max_hp=60,
                  atk=20, dfn=40, sp_atk=20, sp_def=40)
    foe = _mon((WATER_GUN, 0, 0, 0), (25, 0, 0, 0), (WATER, WATER, MYSTERY), battler=1, species=SEAKING,
               personality=2, level=20, hp=60, max_hp=60, atk=20, dfn=40, sp_atk=20, sp_def=20)
    bench = PartyMon(slot=1, species=PAWMOT, level=30, hp=90, max_hp=90, moves=(THUNDERBOLT, 0, 0, 0),
                     pp=(15, 0, 0, 0), status=0, experience=0, friendship=0, nickname="Pawmot", personality=3,
                     atk=40, dfn=40, spd=60, sp_atk=60, sp_def=40)
    assert best_switch([bench], active, [foe], margin=0.25) == 1
    # a mon the type edge already brought in stays unless it is losing, or two edges chain into
    # a switch every turn (Pawmot out for Golduck, Golduck out for Vileplume on one trainer mon)
    assert best_switch([bench], active, [foe], margin=0.25, ko_edge=False) is None
