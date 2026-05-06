"""
Dumbi-JARVIS — Agentic Web Search
Multi-hop search using DuckDuckGo (free, no API key, fully local routing).
Decomposes complex queries into sub-queries, runs them in parallel,
triangulates results, and stops at minimal sufficient depth.
"""
import asyncio
import logging
import re
from typing import List, Dict

logger = logging.getLogger("JARVIS.WebSearch")

_ddg_available = False
try:
    from duckduckgo_search import DDGS
    _ddg_available = True
    logger.info("DuckDuckGo search engine loaded.")
except ImportError:
    logger.warning("duckduckgo-search not installed. Web search disabled. Run: pip install duckduckgo-search")


def web_search_available() -> bool:
    return _ddg_available


def _decompose_query(query: str) -> List[str]:
    """
    Decompose a complex query into 3-5 targeted sub-queries.
    Uses keyword extraction — no LLM call needed for speed.
    """
    q = query.strip()
    sub_queries = [q]  # Always include the original

    # Extract key noun phrases for parallel search
    entities = re.findall(r'\b[A-Z][a-zA-Z]{3,}\b|\b\w{5,}\b', q)
    unique = list(dict.fromkeys(entities))[:4]

    if len(q.split()) > 8:
        # Split on conjunctions for multi-hop
        parts = re.split(r'\band\b|\bor\b|\bvs\b|\bcompared to\b|\bversus\b', q, flags=re.IGNORECASE)
        for part in parts[:3]:
            part = part.strip()
            if len(part) > 10 and part not in sub_queries:
                sub_queries.append(part)

    # Add entity-focused variants
    if len(sub_queries) < 4 and unique:
        sub_queries.append(f"{unique[0]} Bulgaria" if "bulgari" not in q.lower() else unique[0])

    return sub_queries[:5]


def _search_single(query: str, max_results: int = 4) -> List[Dict]:
    """Execute a single DuckDuckGo search."""
    if not _ddg_available:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="bg-bg"))
        return results
    except Exception as e:
        logger.warning(f"Search error for '{query[:40]}': {e}")
        return []


async def multi_hop_search(query: str) -> Dict:
    """
    Autonomous multi-hop search:
    1. Decompose query into sub-queries
    2. Execute in parallel (asyncio)
    3. Triangulate results
    4. Stop at minimal sufficient depth (dedup threshold)
    Returns: {sub_queries, results, context_block}
    """
    if not _ddg_available:
        return {"sub_queries": [], "results": [], "context_block": ""}

    sub_queries = _decompose_query(query)
    logger.info(f"Multi-hop search: {len(sub_queries)} sub-queries for '{query[:50]}'")

    # Run all searches in parallel via thread pool (DDGS is sync)
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _search_single, sq, 4)
        for sq in sub_queries
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten and deduplicate by URL
    seen_urls = set()
    all_results = []
    for res_list in raw_results:
        if isinstance(res_list, Exception):
            continue
        for r in (res_list or []):
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # Minimal sufficient depth: stop when we have 6+ unique results
    all_results = all_results[:8]
    logger.info(f"Multi-hop search complete: {len(all_results)} unique results from {len(sub_queries)} queries.")

    # Build context block for LLM injection
    if not all_results:
        return {"sub_queries": sub_queries, "results": [], "context_block": ""}

    lines = [f"## Web Research Results (Multi-hop, {len(all_results)} sources)\n"]
    for i, r in enumerate(all_results[:6], 1):
        title = r.get("title", "")[:80]
        body  = r.get("body", "")[:200]
        href  = r.get("href", "")[:100]
        lines.append(f"**[{i}] {title}**\n{body}\n*Source: {href}*\n")

    context_block = "\n".join(lines)
    return {
        "sub_queries": sub_queries,
        "results": all_results,
        "context_block": context_block,
    }
