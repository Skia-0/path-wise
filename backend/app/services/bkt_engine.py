"""
Bayesian Knowledge Tracing (BKT) Core Engine.

Models student mastery per topic as a latent binary state (Mastered / Unmastered)
updated probabilistically after every question answer.

Parameters:
- P(L0): Initial probability of mastery (default = 0.20)
- P(T) : Probability of transition / learning per step (default = 0.15)
- P(G) : Probability of guessing correctly when unmastered (default = 0.20)
- P(S) : Probability of slipping / error when mastered (default = 0.10)
"""

DEFAULT_P_INIT = 0.20
DEFAULT_P_TRANSIT = 0.15
DEFAULT_P_GUESS = 0.20
DEFAULT_P_SLIP = 0.10


def update_bkt(
    p_mastery: float,
    is_correct: bool,
    p_transit: float = DEFAULT_P_TRANSIT,
    p_guess: float = DEFAULT_P_GUESS,
    p_slip: float = DEFAULT_P_SLIP,
) -> float:
    """
    Computes updated probability of mastery P(L_t) after observing one answer.
    Pure function with zero side-effects.
    """
    # Clamp initial mastery probability to valid bounds [0.001, 0.999] to avoid div by zero
    p_prior = max(0.001, min(0.999, float(p_mastery)))

    if is_correct:
        # P(L_t-1 | Correct) = [P(L) * (1 - P(S))] / [P(L) * (1 - P(S)) + (1 - P(L)) * P(G)]
        p_obs = (p_prior * (1.0 - p_slip)) / (
            p_prior * (1.0 - p_slip) + (1.0 - p_prior) * p_guess
        )
    else:
        # P(L_t-1 | Incorrect) = [P(L) * P(S)] / [P(L) * P(S) + (1 - P(L)) * (1 - P(G))]
        p_obs = (p_prior * p_slip) / (
            p_prior * p_slip + (1.0 - p_prior) * (1.0 - p_guess)
        )

    # Transition step: P(L_t) = P(L_t-1 | obs) + (1 - P(L_t-1 | obs)) * P(T)
    p_next = p_obs + (1.0 - p_obs) * p_transit

    # Return clamped value between 0.0 and 1.0
    return round(max(0.0, min(1.0, p_next)), 4)


def sequence_bkt(
    answers: list[bool],
    p_init: float = DEFAULT_P_INIT,
    p_transit: float = DEFAULT_P_TRANSIT,
    p_guess: float = DEFAULT_P_GUESS,
    p_slip: float = DEFAULT_P_SLIP,
) -> float:
    """Calculates final mastery after a sequence of answers."""
    p_current = p_init
    for ans in answers:
        p_current = update_bkt(
            p_mastery=p_current,
            is_correct=ans,
            p_transit=p_transit,
            p_guess=p_guess,
            p_slip=p_slip,
        )
    return p_current


def get_bkt_tier(p_mastery: float) -> str:
    """Maps BKT mastery probability to student tier."""
    if p_mastery >= 0.70:
        return "Advanced"
    elif p_mastery >= 0.40:
        return "Intermediate"
    return "Beginner"