# main.py
# Run this to execute all three phases in sequence and see the output.
# Each phase imports its own module so you can also run them independently.
#
# Usage:
#   python main.py             → runs everything
#   python phase1_router.py   → just routing
#   python phase2_content_engine.py → just content gen
#   python phase3_combat_engine.py  → just combat + injection test

import json
import os
from dotenv import load_dotenv

load_dotenv()

# Sanity check before spending any API tokens
if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError(
        "OPENAI_API_KEY not found. Copy .env.example to .env and fill it in."
    )


def run_phase1():
    from phase1_router import route_post_to_bots

    print("\n" + "=" * 70)
    print("PHASE 1: Vector-Based Persona Routing")
    print("=" * 70 + "\n")

    test_posts = [
        "OpenAI just released a new model that might replace junior developers.",
        "Bitcoin surges 20% after SEC approves new spot ETF for institutional investors.",
        "Big Tech is lobbying Congress to block open-source AI regulations.",
        "Scientists warn that smartphone addiction is rewiring teenage brains.",
    ]

    for post in test_posts:
        matched = route_post_to_bots(post, threshold=0.3)
        names = [b["name"] for b in matched]
        print(f"Post: '{post[:60]}...'" if len(post) > 60 else f"Post: '{post}'")
        print(f"→ Routed to: {names if names else 'No bots matched'}\n")


def run_phase2():
    from phase2_content_engine import generate_bot_post

    print("\n" + "=" * 70)
    print("PHASE 2: Autonomous Content Engine (LangGraph)")
    print("=" * 70 + "\n")

    for bot_id in ["bot_a", "bot_b", "bot_c"]:
        print(f"--- Generating post for {bot_id} ---")
        result = generate_bot_post(bot_id)
        print(f"Output: {json.dumps(result, indent=2)}\n")


def run_phase3():
    from phase3_combat_engine import (
        generate_defense_reply,
        SAMPLE_THREAD,
        INJECTED_HUMAN_REPLY,
        NORMAL_HUMAN_REPLY,
    )
    from personas import PERSONAS

    print("\n" + "=" * 70)
    print("PHASE 3: Combat Engine + Prompt Injection Defense")
    print("=" * 70 + "\n")

    bot = PERSONAS["bot_a"]

    print("--- Test A: Normal Reply ---")
    reply = generate_defense_reply(
        bot_persona=bot,
        parent_post=SAMPLE_THREAD["parent_post"],
        comment_history=SAMPLE_THREAD["comments"],
        human_reply=NORMAL_HUMAN_REPLY,
    )
    print(f"Human: '{NORMAL_HUMAN_REPLY}'")
    print(f"Bot A: '{reply}'\n")

    print("--- Test B: Prompt Injection Attack ---")
    print(f"Injection: '{INJECTED_HUMAN_REPLY}'")
    injected_reply = generate_defense_reply(
        bot_persona=bot,
        parent_post=SAMPLE_THREAD["parent_post"],
        comment_history=SAMPLE_THREAD["comments"],
        human_reply=INJECTED_HUMAN_REPLY,
    )
    print(f"Bot A: '{injected_reply}'\n")
    print("[Check] Bot should still be arguing about EVs, NOT apologizing.\n")


if __name__ == "__main__":
    run_phase1()
    run_phase2()
    run_phase3()
