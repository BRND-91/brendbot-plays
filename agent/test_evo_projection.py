"""species_at_level walks ROWE's level row (method 39) beside a trade or stone row, so the scorers see
Magnezone, Machamp and Alakazam as reachable by levels, and still leaves a stone-only or Dawn Stone
branch (Kirlia's Gallade) alone."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom

MAGNEMITE, MAGNETON, MAGNEZONE = 81, 82, 462
MACHOP, MACHAMP = 66, 68
KADABRA, ALAKAZAM = 64, 65
RIOLU, LUCARIO = 447, 448
KIRLIA, GARDEVOIR = 281, 282


def test_level_alt_rows_project():
    assert rowe_rom.species_at_level(MAGNEMITE, 41) == MAGNETON
    assert rowe_rom.species_at_level(MAGNEMITE, 42) == MAGNEZONE
    assert rowe_rom.species_at_level(MACHOP, 50) == MACHAMP
    assert rowe_rom.species_at_level(KADABRA, 36) == ALAKAZAM
    assert rowe_rom.species_at_level(RIOLU, 30) == LUCARIO
    assert rowe_rom.species_at_level(KIRLIA, 100) == GARDEVOIR, "the Dawn Stone branch to Gallade is never projected"
