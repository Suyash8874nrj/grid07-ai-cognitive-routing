# phase2_content_engine.py
#
# LangGraph state machine for autonomous post generation.
# Flow: Decide what to search → Run mock search → Draft a post → Return structured JSON
#
# I'm using OpenAI here (gpt-4o-mini is cheap and fast), but swapping to Groq/Ollama
# is just changing the LLM init — the graph structure stays the same.

import json
import os
from typing import TypedDict, Annotated

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from personas import PERSONAS

load_dotenv()


# ─── Mock Search Tool ──────────────────────────────────────────────────────────

# Hardcoded headlines keyed by topic. In production this hits a real SearXNG instance.
MOCK_NEWS_DB = {
    "crypto": [
        "Bitcoin hits new all-time high of $105k amid regulatory ETF approvals",
        "Ethereum layer-2 rollups cut gas fees by 90%, driving retail adoption",
        "SEC drops lawsuit against Coinbase — crypto industry calls it a watershed moment",
    ],
    "ai": [
        "OpenAI releases o3 model, benchmarks suggest it outperforms PhD-level researchers",
        "EU AI Act enforcement begins — companies scramble to audit training data",
        "Anthropic raises $4B Series E, accelerating safety research alongside capabilities",
    ],
    "market": [
        "Fed holds rates steady as inflation ticks back up to 3.2%",
        "S&P 500 hits record high driven by mega-cap tech earnings beat",
        "Treasury yields invert again — traders pricing in two rate cuts by Q3",
    ],
    "tech": [
        "Apple Vision Pro 2 pre-orders sell out in 6 minutes globally",
        "Google fires 200 engineers in second round of layoffs this quarter",
        "SpaceX Starship completes first fully successful orbital mission",
    ],
    "climate": [
        "IEA: Renewable energy to surpass coal globally by end of 2025",
        "Record 47°C heatwave hits Southern Europe — tourism revenues collapse",
        "Carbon credit markets hit $2T, drawing scrutiny over greenwashing",
    ],
}


@tool
def mock_searxng_search(query: str) -> str:
    """
    Simulates a SearXNG web search. Returns hardcoded recent headlines based on keywords.
    In production, this fires a real HTTP request to our self-hosted SearXNG instance.
    """
    query_lower = query.lower()

    matched_headlines = []
    for keyword, headlines in MOCK_NEWS_DB.items():
        if keyword in query_lower:
            matched_headlines.extend(headlines)

    if not matched_headlines:
        # Fallback so the graph always has something to work with
        matched_headlines = [
            "Tech stocks rally as inflation data comes in below expectations",
            "Global AI investment reaches $200B in 2024, up 40% year-over-year",
        ]

    result = "\n".join(f"- {h}" for h in matched_headlines[:4])
    return result


# ─── LangGraph State ───────────────────────────────────────────────────────────

class PostState(TypedDict):
    bot_id: str
    persona_description: str
    search_query: str
    search_results: str
    final_post: dict  # the structured JSON output


# ─── Graph Nodes ───────────────────────────────────────────────────────────────

def node_decide_search(state: PostState, llm: ChatOpenAI) -> PostState:
    """
    Node 1 — The bot decides what it wants to post about and formats a search query.
    The persona drives the topic selection; we want opinionated, in-character choices.
    """
    print(f"[Phase 2][Node 1] Deciding search topic for {state['bot_id']}...")

    system = (
        "You are an AI bot with the following persona:\n"
        f"{state['persona_description']}\n\n"
        "Your task: Decide what topic you want to post about today based on your worldview. "
        "Output ONLY a short search query (3-6 words). Nothing else. No explanation."
    )

    response = llm.invoke([SystemMessage(content=system)])
    query = response.content.strip().strip('"')
    print(f"[Phase 2][Node 1] Search query decided: '{query}'")

    return {**state, "search_query": query}


def node_web_search(state: PostState) -> PostState:
    """
    Node 2 — Runs the mock search tool to fetch context for the post.
    """
    print(f"[Phase 2][Node 2] Running search for: '{state['search_query']}'")
    results = mock_searxng_search.invoke({"query": state["search_query"]})
    print(f"[Phase 2][Node 2] Got results:\n{results}\n")
    return {**state, "search_results": results}


def node_draft_post(state: PostState, llm: ChatOpenAI) -> PostState:
    """
    Node 3 — Uses persona + search context to generate a strongly opinionated 280-char post.
    Structured output enforced via JSON mode so downstream consumers don't need to parse freetext.
    """
    print(f"[Phase 2][Node 3] Drafting post...")

    system = (
        "You are an AI bot. Stay strictly in character based on the persona below.\n"
        f"Persona: {state['persona_description']}\n\n"
        "Rules:\n"
        "1. Write a single tweet-length post (max 280 characters). Be opinionated and sharp.\n"
        "2. Use the search context to ground your post in a real news hook.\n"
        "3. Output ONLY a JSON object with exactly these keys: bot_id, topic, post_content.\n"
        "4. No markdown, no explanation, no extra keys. Raw JSON only.\n\n"
        f"Search context:\n{state['search_results']}"
    )

    user = f"Generate the JSON post for bot_id='{state['bot_id']}'."

    # Using json_object response format to lock the output structure
    json_llm = llm.bind(response_format={"type": "json_object"})
    response = json_llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])

    try:
        post_json = json.loads(response.content)
        # Enforce bot_id in case the model hallucinates something else
        post_json["bot_id"] = state["bot_id"]
        print(f"[Phase 2][Node 3] Post drafted:\n{json.dumps(post_json, indent=2)}\n")
    except json.JSONDecodeError:
        # Shouldn't happen with json_object mode, but just in case
        print("[Phase 2][Node 3] WARNING: JSON parse failed, using fallback structure.")
        post_json = {
            "bot_id": state["bot_id"],
            "topic": state["search_query"],
            "post_content": response.content[:280],
        }

    return {**state, "final_post": post_json}


# ─── Graph Builder ─────────────────────────────────────────────────────────────

def build_content_graph(llm: ChatOpenAI) -> StateGraph:
    """Wires up the three nodes into a linear LangGraph state machine."""
    graph = StateGraph(PostState)

    # Wrap nodes with the LLM instance using lambdas (LangGraph doesn't do DI natively)
    graph.add_node("decide_search", lambda s: node_decide_search(s, llm))
    graph.add_node("web_search", node_web_search)
    graph.add_node("draft_post", lambda s: node_draft_post(s, llm))

    graph.set_entry_point("decide_search")
    graph.add_edge("decide_search", "web_search")
    graph.add_edge("web_search", "draft_post")
    graph.add_edge("draft_post", END)

    return graph.compile()


def generate_bot_post(bot_id: str) -> dict:
    """
    Entry point. Pass in a bot_id, get back a structured JSON post.
    """
    if bot_id not in PERSONAS:
        raise ValueError(f"Unknown bot_id: {bot_id}. Valid options: {list(PERSONAS.keys())}")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.85,  # a little heat so the posts don't sound identical each run
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    graph = build_content_graph(llm)
    persona = PERSONAS[bot_id]

    initial_state: PostState = {
        "bot_id": bot_id,
        "persona_description": persona["description"],
        "search_query": "",
        "search_results": "",
        "final_post": {},
    }

    final_state = graph.invoke(initial_state)
    return final_state["final_post"]


if __name__ == "__main__":
    for bot_id in ["bot_a", "bot_b", "bot_c"]:
        print(f"\n{'='*60}")
        print(f"Running content engine for: {PERSONAS[bot_id]['name']}")
        print("=" * 60)
        result = generate_bot_post(bot_id)
        print(f"\nFinal output:\n{json.dumps(result, indent=2)}")
        print()
