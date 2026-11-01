"""Player._switch_budget caps matchup-switch retries for one active mon. A switch issued for the
mon that chose last turn never put a new one out (a double-battle send the party menu could not
land), so repeats spend the budget and the chooser falls through to Fight instead of looping it."""
from play import Player, SWITCH_FAIL_CAP


def _player() -> Player:
    p = Player.__new__(Player)
    p._switch_active = None
    p._switch_fails = 0
    return p


def main() -> None:
    p = _player()
    tries = [p._switch_budget("Pidgeotto") for _ in range(SWITCH_FAIL_CAP + 2)]
    assert tries[:SWITCH_FAIL_CAP] == [True] * SWITCH_FAIL_CAP, f"first {SWITCH_FAIL_CAP} allowed: {tries}"
    assert tries[SWITCH_FAIL_CAP] is False, "the budget denies the switch once the same mon loops"
    assert tries[SWITCH_FAIL_CAP + 1] is False, "stays denied while that mon is still out"

    # a different active mon is a fresh matchup, so the budget resets to a full allowance
    assert p._switch_budget("Taillow") is True, "a new active resets the budget"
    assert p._switch_fails == 0

    print("test_switch_budget: ok")


if __name__ == "__main__":
    main()
