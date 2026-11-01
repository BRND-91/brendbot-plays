"""Write the Sootopolis gym (15,0) cover route into gym_routes.json for the live bot.

solve_sootopolis_ice plans the per-room Hamiltonian ice cover from the door; probe_sootopolis_bfs's
replay() runs those presses once from the frozen entry fixture and records the full (x, y, group, num)
before each press and after the last, the keys Errands.follow_route resumes on. Reusing the probe's
writer keeps the on-disk schema identical to the Lavaridge route and validates the climb to Juan's
tile before it writes.

    .venv/bin/python write_sootopolis_route.py
"""
import emu_boot as eb
import probe_sootopolis_bfs as P
import solve_sootopolis_ice as S
from nav import Grid


def main() -> None:
    e = eb.Emu()
    e.load_state(open(S.ENTRY, "rb").read())
    presses = S.to_presses(S.plan(Grid(e)))
    player = P.make_player(e)
    P.replay(player, [list(p) for p in presses])


if __name__ == "__main__":
    main()
