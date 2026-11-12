"""Tests for assignment generation and interactive setup state."""

import pytest

from SecretSanta import DrawParticipant, DrawSetupView, _make_assignments, _rotate_list
from conftest import MockMember


def test_rotate_list():
    assert _rotate_list([1, 2, 3], 1) == [3, 1, 2]
    assert _rotate_list([1, 2, 3], 2) == [2, 3, 1]
    assert _rotate_list([], 1) == []


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_make_assignments_is_a_derangement(count):
    participants = [MockMember(index, f"Person{index}") for index in range(count)]
    result = _make_assignments(participants)

    assert result is not None
    assert len(result) == count
    assert all(giver.id != receiver.id for giver, receiver in result)
    assert {giver.id for giver, _ in result} == {receiver.id for _, receiver in result}


def test_make_assignments_respects_independent_exclusion_pairs():
    participants = [MockMember(index, f"Person{index}") for index in range(4)]
    exclusions = {frozenset((0, 1)), frozenset((2, 3))}

    result = _make_assignments(participants, exclusions=exclusions)

    assert result is not None
    assert all(
        frozenset((giver.id, receiver.id)) not in exclusions
        for giver, receiver in result
    )


def test_draw_setup_includes_external_users_in_participant_picker():
    role = type("Role", (), {"name": "Participants"})()
    members = [MockMember(1, "Server user")]
    setup = DrawSetupView(1, role, members)
    setup.external_users.append(MockMember(2, "External user"))

    assert [participant.id for participant in setup.all_participants] == [1, 2]


def test_external_participant_uses_draw_nickname():
    user = MockMember(2, "Discord username")
    participant = DrawParticipant(user, "Secret Santa nickname")

    assert participant.id == user.id
    assert participant.display_name == "Secret Santa nickname"


@pytest.mark.parametrize("count", [3, 4, 5, 7])
def test_make_assignments_single_cycle(count):
    participants = [MockMember(index, f"Person{index}") for index in range(count)]
    result = _make_assignments(participants, single_cycle=True)

    assert result is not None
    by_giver = {giver.id: receiver.id for giver, receiver in result}
    start = result[0][0].id
    current = start
    seen = set()
    while current not in seen:
        seen.add(current)
        current = by_giver[current]
    assert current == start
    assert len(seen) == count
