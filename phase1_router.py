# Mock version of phase1_router.py (NO chromadb needed)

PERSONAS = {
    "Tech Maximalist": ["AI", "technology", "OpenAI", "developers"],
    "Doomer / Skeptic": ["regulation", "danger", "addiction", "privacy"],
    "Finance Bro": ["bitcoin", "market", "stocks", "ETF", "rates"]
}

def route_post_to_bots(post_content, threshold=0.3):
    post_content = post_content.lower()
    matched_bots = []

    print(f"[Phase 1] Routing post: '{post_content}'\n")

    for persona, keywords in PERSONAS.items():
        score = sum(1 for word in keywords if word.lower() in post_content)

        if score > 0:
            matched_bots.append(persona)
            print(f"✓ {persona} matched (score={score})")
        else:
            print(f"✗ {persona} skipped")

    print()
    return matched_bots