"""A field dispatcher's sailor hides behind a visibility flag at a story phase (the (1,9) sailor's
flag 0xDF3 sets at 12 badges), so talk_object still finds it in the ROM table but there is no NPC to
talk to. _object_hidden reads the object's flag and the live flag state so _cross_to gates the arm
instead of mashing A into the gap, which no_menu-looped the run back to One Island."""
import types

import play
import rowe_rom


def _player(flag_state: dict):
    p = play.Player.__new__(play.Player)
    p.g = types.SimpleNamespace(flag=lambda f: flag_state.get(f, False))
    return p


def test_object_with_a_set_flag_reads_hidden(monkeypatch):
    # the sailor template at (40,7) carries visibility flag 0xDF3
    monkeypatch.setattr(rowe_rom, "map_objects", lambda g, n: [(40, 7, 7, 0xDF3)])
    assert _player({0xDF3: True})._object_hidden((1, 9), (40, 7)) is True
    assert _player({0xDF3: False})._object_hidden((1, 9), (40, 7)) is False


def test_object_with_no_flag_is_never_hidden(monkeypatch):
    # a flagless object (flag 0) is always present; a set flag it does not carry does not hide it
    monkeypatch.setattr(rowe_rom, "map_objects", lambda g, n: [(8, 10, 7, 0)])
    assert _player({0xDF3: True})._object_hidden((9, 9), (8, 10)) is False


def test_object_absent_from_the_table_reads_present(monkeypatch):
    monkeypatch.setattr(rowe_rom, "map_objects", lambda g, n: [(1, 1, 0, 0xDF3)])
    assert _player({0xDF3: True})._object_hidden((1, 9), (40, 7)) is False
