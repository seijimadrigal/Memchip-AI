"""Retriever: FTS5 search + multi-hop expansion."""
from __future__ import annotations
from .storage import RawTextStore
from .query_parser import parse_query, _get_nlp


def retrieve(store: RawTextStore, question: str, max_candidates: int = 80) -> list[dict]:
    """Retrieve candidate passages using FTS5 + entity search + multi-hop expansion.
    
    Returns list of chunk dicts with text, session_id, date, etc.
    """
    nlp = _get_nlp()
    
    # Parse query into weighted terms
    parsed = parse_query(question)
    terms = [t for t, w in parsed]
    
    if not terms:
        # Fallback: use all non-stop words
        doc = nlp(question)
        terms = [tok.text for tok in doc if not tok.is_stop and not tok.is_punct and len(tok.text) > 1]
    
    # Extract person names from question — always search for these
    doc = nlp(question)
    person_names = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    
    # First pass: FTS5 search with all terms
    results = store.search_fts(terms, limit=max_candidates)
    seen_ids = {r["id"] for r in results}
    
    # Second pass: search by person name alone (catches ALL mentions of that person)
    for name in person_names:
        name_results = store.search_fts([name], limit=50)
        for r in name_results:
            if r["id"] not in seen_ids:
                results.append(r)
                seen_ids.add(r["id"])
    
    if not results:
        # Fallback: try individual high-weight terms
        for term, weight in parsed[:3]:
            r = store.search_fts([term], limit=20)
            for rr in r:
                if rr["id"] not in seen_ids:
                    results.append(rr)
                    seen_ids.add(rr["id"])
    
    # Multi-hop: extract new entities from results, search again
    if results:
        new_entities = set()
        
        # Only look at top results for entity expansion
        top_texts = " ".join(r["text"] for r in results[:10])
        doc = nlp(top_texts)
        
        original_terms_lower = {t.lower() for t in terms}
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "LOC", "FAC", "EVENT", "WORK_OF_ART"):
                if ent.text.lower() not in original_terms_lower:
                    new_entities.add(ent.text)
        
        # Search with new entities
        if new_entities:
            hop2 = store.search_fts(list(new_entities), limit=20)
            for r in hop2:
                if r["id"] not in seen_ids:
                    results.append(r)
                    seen_ids.add(r["id"])
    
    # Deduplicate by id
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    
    return deduped[:max_candidates]
