"""trainer_pool reads a gym leader's rows off the ROM's gTrainers layout and leader_team rebuilds the
fight the live log recorded: Winona at 4 badges fielded Doduo, Sigilyph, Murkrow, Swablu w/ Doduo at
L26, and every mon Flannery can field at 6 badges is Fire or Dark/Fire."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom

DODUO, MURKROW, SIGILYPH, SKARMORY, DRATINI, SWABLU = 84, 198, 561, 227, 147, 333
VULPIX, FLETCHLING, SALANDIT, SCORBUNNY, HOUNDOUR, TORKOAL = 37, 661, 757, 813, 228, 324
FLETCHINDER, SALAZZLE, CINDERACE = 662, 758, 815
INDEEDEE, FORM_1800, SOLROCK, LUNATONE = 876, 1800, 338, 337


def main() -> None:
    assert rowe_rom.trainer_pool("Winona") == [DODUO, MURKROW, SIGILYPH, SKARMORY, DRATINI, SWABLU]
    team = rowe_rom.leader_team("Winona", 4)
    assert sorted(sp for sp, _ in team) == sorted([DODUO, MURKROW, SIGILYPH, SWABLU]), team
    assert team[0] == (DODUO, 26), team
    assert team[-1] == (SWABLU, 29), team

    flannery = rowe_rom.leader_team("Flannery", 6)
    base = rowe_rom.LEADER_BASE_LEVEL[6]
    assert flannery == [(VULPIX, base), (FLETCHLING, base + 1), (SALANDIT, base + 2), (SCORBUNNY, base + 3), (TORKOAL, base + 4)], flannery
    assert HOUNDOUR not in [sp for sp, _ in flannery], "row 4 is skipped at count 5"
    # Salandit's only step is EVO_LEVEL_FEMALE (16), which the EVO_LEVEL walk leaves alone
    assert rowe_rom.leader_build("Flannery", 6) == [(VULPIX, 33), (FLETCHINDER, 34), (SALANDIT, 35), (CINDERACE, 36), (TORKOAL, 37)]
    assert rowe_rom.evolutions(SALANDIT) == ((16, 33, SALAZZLE),)

    pair = rowe_rom.leader_team("Tate&Liza", 5)
    assert [sp for sp, _ in pair] == [INDEEDEE, FORM_1800, SOLROCK, LUNATONE], f"rows 0, 1, 4, 5 at count 4, got {pair}"
    assert rowe_rom.trainer_struct("Tate&Liza") == 0x3FEA98
    assert rowe_rom.LEADERS[7] == "Juan" and rowe_rom.LEAGUE[-1] == "Wallace"
    assert len(rowe_rom.leader_build("Wallace", 8)) == 6
    print("ok")


if __name__ == "__main__":
    main()
