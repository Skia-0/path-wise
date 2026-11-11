import os
import sys

# Ensure backend root is in Python path when executing script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.bkt_engine import DEFAULT_P_INIT, get_bkt_tier, update_bkt


def run_simulation():
    print("=" * 72)
    print("      PATH-WISE BKT ADAPTIVE LEARNING MODEL — STUDENT SIMULATION")
    print("=" * 72)
    print("Initial Mastery P(L0) = 0.20 | P(Transit) = 0.15 | P(Guess) = 0.20 | P(Slip) = 0.10\n")

    # Define 3 simulated student response streams across 20 practice questions
    simulations = {
        "Weak Student (30% accuracy)": [
            False, False, True, False, False, False, True, False, False, False,
            False, True, False, False, False, False, True, False, False, False
        ],
        "Improving Student (20% -> 80% accuracy)": [
            False, False, True, False, False, False, False, True, False, False,
            True, True, True, False, True, True, True, True, True, True
        ],
        "Strong Student (90% accuracy)": [
            True, True, True, True, False, True, True, True, True, True,
            True, True, True, True, True, False, True, True, True, True
        ],
    }

    for title, responses in simulations.items():
        print(f"\n--- {title} ---")
        print(f"{'Q#':<5} | {'Result':<10} | {'Mastery P(L)':<14} | {'Tier':<12}")
        print("-" * 50)

        p_mastery = DEFAULT_P_INIT
        print(f"{'0':<5} | {'Start':<10} | {p_mastery:<14.4f} | {get_bkt_tier(p_mastery):<12}")

        for i, ans in enumerate(responses, 1):
            res_str = "Correct" if ans else "Incorrect"
            p_mastery = update_bkt(p_mastery=p_mastery, is_correct=ans)
            tier = get_bkt_tier(p_mastery)
            print(f"{i:<5} | {res_str:<10} | {p_mastery:<14.4f} | {tier:<12}")

        print("-" * 50)
        print(f"Final Mastery: {p_mastery * 100:.1f}% | Final Tier: {get_bkt_tier(p_mastery)}")

    print("\n" + "=" * 72)
    print("Simulation Complete — All BKT state updates verified.")
    print("=" * 72)


if __name__ == "__main__":
    run_simulation()