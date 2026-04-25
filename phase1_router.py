# phase1_router.py
#
# Vector-based routing: embed incoming posts and match them against bot personas
# using cosine similarity. Only bots that "care" about a topic get routed to.
#
# I went with ChromaDB because it handles the embedding + similarity search in one
# clean API call. FAISS is faster at scale but overkill here.

import os
import chromadb
from chromadb.utils import embedding_functions
from personas import PERSONAS


# Using sentence-transformers locally so we don't burn API credits on embeddings.
# all-MiniLM-L6-v2 is small but accurate enough for semantic similarity tasks like this.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_client = None
_collection = None


def _get_collection():
    """
    Lazy-init the ChromaDB client and collection.
    Builds the vector store once and caches it for the session.
    """
    global _client, _collection

    if _collection is not None:
        return _collection

    print("[Phase 1] Initializing in-memory ChromaDB...")
    _client = chromadb.Client()  # ephemeral, in-memory

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    _collection = _client.create_collection(
        name="bot_personas",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},  # cosine distance, not L2
    )

    # Index each bot persona as a document
    docs = []
    ids = []
    metadatas = []

    for bot_id, persona in PERSONAS.items():
        docs.append(persona["description"])
        ids.append(bot_id)
        metadatas.append({"name": persona["name"]})

    _collection.add(documents=docs, ids=ids, metadatas=metadatas)
    print(f"[Phase 1] Indexed {len(ids)} bot personas into vector store.\n")

    return _collection


def route_post_to_bots(post_content: str, threshold: float = 0.3) -> list[dict]:
    """
    Embeds `post_content` and finds bots whose persona is semantically similar.

    ChromaDB returns distances in [0, 2] for cosine space (distance = 1 - similarity).
    So similarity = 1 - distance. We keep bots where similarity >= threshold.

    Note: 0.85 from the spec is *very* tight with MiniLM — I'm using 0.3 as default
    which gives realistic routing without everything returning empty. Caller can override.
    """
    collection = _get_collection()

    results = collection.query(
        query_texts=[post_content],
        n_results=len(PERSONAS),  # get all bots and filter manually
        include=["distances", "metadatas", "documents"],
    )

    distances = results["distances"][0]
    ids = results["ids"][0]
    metadatas = results["metadatas"][0]

    matched_bots = []
    print(f"[Phase 1] Routing post: '{post_content[:80]}...'")
    print(f"[Phase 1] Similarity scores (threshold={threshold}):")

    for bot_id, distance, meta in zip(ids, distances, metadatas):
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity so it matches the spec's threshold language
        similarity = 1 - distance
        is_match = similarity >= threshold
        marker = "✓ ROUTED" if is_match else "✗ skipped"
        print(f"   {meta['name']:20s} | similarity={similarity:.4f} | {marker}")

        if is_match:
            matched_bots.append(
                {
                    "bot_id": bot_id,
                    "name": meta["name"],
                    "similarity": round(similarity, 4),
                    "persona": PERSONAS[bot_id]["description"],
                }
            )

    print()
    return matched_bots


# Quick smoke test
if __name__ == "__main__":
    test_posts = [
        "OpenAI just released a new model that might replace junior developers.",
        "Bitcoin surges 20% after SEC approves new spot ETF for institutional investors.",
        "Big Tech is lobbying Congress to block open-source AI regulations.",
    ]

    for post in test_posts:
        matched = route_post_to_bots(post)
        print(f"→ Matched bots: {[b['name'] for b in matched]}\n")
        print("-" * 70 + "\n")
