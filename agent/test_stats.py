"""stats_at reproduces the game's stat formula on two fixture party mons whose six stats the save shows
(catch_switch.ss slots 1 and 4, EVs off bytes 0x20, nature off personality, 0 skill levels), and
species_at_level walks EVO_LEVEL rows only: Trubbish turns Garbodor at 36, Bulbasaur reaches Venusaur
at 32, Vulpix stays Vulpix at any level since its rows are item and map gated."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom

FLETCHINDER, TRUBBISH, GARBODOR, BULBASAUR, IVYSAUR, VENUSAUR, VULPIX, MARILL, AZUMARILL = 662, 568, 569, 1, 2, 3, 37, 183, 184
GREEDENT = 820
NO_IVS = (0, 0, 0, 0, 0, 0)


def main() -> None:
    assert rowe_rom.stats_at(FLETCHINDER, 21, 16, NO_IVS, (91, 99, 48, 140, 12, 58)) == (61, 40, 27, 47, 31, 29)
    assert rowe_rom.stats_at(TRUBBISH, 24, 18, NO_IVS, (91, 136, 31, 181, 27, 44)) == (63, 37, 36, 47, 25, 37)
    # city_gate.ss slot 1 Greedent at 3 badges, iv_boosts read (24, 15, 15, 12, 12, 12) off the skill rows
    assert rowe_rom.stats_at(GREEDENT, 31, 18, (24, 15, 15, 12, 12, 12), (89, 127, 21, 200, 45, 28)) == (129, 78, 70, 36, 46, 57)
    assert rowe_rom.stats_at(GREEDENT, 31, 18, NO_IVS, (89, 127, 21, 200, 45, 28)) != (129, 78, 70, 36, 46, 57), \
        "the skill boosts are what close the gap, so zero IVs must miss"

    assert rowe_rom.species_at_level(TRUBBISH, 35) == TRUBBISH
    assert rowe_rom.species_at_level(TRUBBISH, 36) == GARBODOR
    assert rowe_rom.species_at_level(BULBASAUR, 16) == IVYSAUR
    assert rowe_rom.species_at_level(BULBASAUR, 32) == VENUSAUR
    assert rowe_rom.species_at_level(VULPIX, 60) == VULPIX
    assert rowe_rom.species_at_level(MARILL, 18) == AZUMARILL
    assert rowe_rom.evolutions(MARILL) == ((rowe_rom.EVO_LEVEL, 18, AZUMARILL),)

    assert rowe_rom.species(BULBASAUR).abilities == (65, 94, 34)
    assert rowe_rom.ability_of(BULBASAUR, 2) == 34
    assert rowe_rom.ability_of(FLETCHINDER, 1) == rowe_rom.species(FLETCHINDER).abilities[0], "an empty slot 1 falls back to slot 0"
    print("ok")


if __name__ == "__main__":
    main()
