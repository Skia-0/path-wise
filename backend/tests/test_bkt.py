import pytest
from app.services.bkt_engine import (
    DEFAULT_P_INIT,
    get_bkt_tier,
    sequence_bkt,
    update_bkt,
)


def test_bkt_correct_answer_increases_mastery():
    p_initial = DEFAULT_P_INIT  # 0.20
    p_updated = update_bkt(p_mastery=p_initial, is_correct=True)

    assert p_updated > p_initial
    # With defaults: P(L_obs) = (0.2*0.9)/(0.2*0.9 + 0.8*0.2) = 0.18 / 0.34 = 0.5294
    # P(L_next) = 0.5294 + (1-0.5294)*0.15 = 0.6000
    assert pytest.approx(p_updated, 0.01) == 0.6000


def test_bkt_incorrect_answer_decreases_mastery():
    p_initial = 0.60
    p_updated = update_bkt(p_mastery=p_initial, is_correct=False)

    assert p_updated < p_initial


def test_bkt_streak_correct_approaches_one():
    streak = [True] * 10
    final_mastery = sequence_bkt(streak, p_init=0.20)

    assert final_mastery >= 0.95
    assert get_bkt_tier(final_mastery) == "Advanced"


def test_bkt_streak_incorrect_stays_low():
    streak = [False] * 10
    final_mastery = sequence_bkt(streak, p_init=0.50)

    assert final_mastery < 0.30
    assert get_bkt_tier(final_mastery) == "Beginner"


def test_bkt_tier_thresholds():
    assert get_bkt_tier(0.20) == "Beginner"
    assert get_bkt_tier(0.39) == "Beginner"
    assert get_bkt_tier(0.40) == "Intermediate"
    assert get_bkt_tier(0.69) == "Intermediate"
    assert get_bkt_tier(0.70) == "Advanced"
    assert get_bkt_tier(0.95) == "Advanced"