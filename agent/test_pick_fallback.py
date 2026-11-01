"""pick_move falls back here when scoring leaves nothing; confirming a 0-PP slot makes the
game reject the move ("no PP left for this move!") and wedges the action menu, the Pawmot vs
Donphan loop on stream. The fallback must never hand back a spent slot while a move with PP
exists."""
from battle_engine import first_usable_slot


def main() -> None:
    # slot 0 present but spent (Supercell Slam pp 0), slot 1 has PP: never return 0
    assert first_usable_slot([1, 2, 0, 0], [0, 5, 0, 0]) == 1, "returned a spent slot"
    # among usable moves, the most-PP one, so the menu never re-nags on a near-empty slot
    assert first_usable_slot([1, 2, 3, 4], [1, 9, 0, 3]) == 1, "did not pick the most-PP move"
    # no move has PP anywhere: the game auto-Struggles, the menu never shows, 0 is harmless
    assert first_usable_slot([1, 2, 0, 0], [0, 0, 0, 0]) == 0, "invented PP where there is none"
    # an empty slot (move id 0) is never selected even if its pp reads nonzero garbage
    assert first_usable_slot([0, 2, 0, 0], [7, 4, 0, 0]) == 1, "selected an empty move slot"
    print("ok")


if __name__ == "__main__":
    main()
