"""Run the live gym loop on a copy of a snapshot inside the Seven Island gym (2,13) until the badge
lands or the step budget runs out, the control for the ice-slide pathing: gym_step plans the walk,
battle_step plays the trainer and leader fights the walk opens.

    probe_ice_slide.py [state, default /tmp/rowe_213_probe.ss]
"""
import sys

import emu_boot as eb
import play

STATE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/rowe_213_probe.ss"
GYM = (2, 13)
STEPS = 400


def main() -> None:
    e = eb.Emu()
    e.load_state(open(STATE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=STATE + ".caught.json")
    p.goal = {"mode": "gym", "map": list(GYM), "badges": p.g.badges(), "stand": [5, 4]}
    start = p.g.badges()
    streak = 0
    for i in range(STEPS):
        if p.g.in_battle():
            p.battle_step()
            streak = p.stall_check(p.battle_signature(), streak)
            continue
        streak = 0
        if p.g.badges() > start:
            print(f"BADGE after {i} steps at {p.g.position()}", flush=True)
            return
        try:
            p.gym_step()
        except play.GoalExit as ex:
            print(f"goal exit: {ex} at {p.g.position()}", flush=True)
            return
    print(f"NO BADGE after {STEPS} steps at {p.g.position()}, badges {p.g.badges()}", flush=True)


if __name__ == "__main__":
    main()
