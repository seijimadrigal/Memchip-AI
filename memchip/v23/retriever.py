"""NER-weighted retrieval with multi-hop expansion (SmartSearch-style)."""
from __future__ import annotations
from .storage import RawTextStore
from .query_parser import parse_query, extract_entities, _get_nlp


def retrieve(store: RawTextStore, question: str, max_candidates: int = 200) -> list[dict]:
    """Retrieve candidates using NER-weighted FTS5 + multi-hop expansion.
    
    Key differences from v3:
    - NER-weighted term extraction (PROPN 3x, entities 4x)  
    - Substring fallback for terms FTS5 misses
    - Multi-hop entity expansion from top results
    - Higher candidate count (200 vs 80)
    """
    parsed = parse_query(question)
    
    if not parsed:
        nlp = _get_nlp()
        doc = nlp(question)
        parsed = [(tok.text.lower(), 1.0) for tok in doc 
                   if not tok.is_stop and not tok.is_punct and len(tok.text) > 1]
    
    # Extract person names for targeted search
    entities = extract_entities(question)
    person_names = [e[0] for e in entities if e[1] == "PERSON"]
    
    seen_ids = set()
    results = []
    
    def _add_results(new_results):
        for r in new_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append(r)
    
    # === Pass 1: All weighted terms via FTS5 (OR query) ===
    all_terms = [t for t, w in parsed]
    _add_results(store.search_fts(all_terms, limit=max_candidates))
    
    # === Pass 2: High-weight terms individually (PROPN, entities) ===
    high_weight = [(t, w) for t, w in parsed if w >= 2.5]
    for term, weight in high_weight:
        _add_results(store.search_fts([term], limit=50))
    
    # === Pass 3: Person names via substring (catches partial matches FTS misses) ===
    for name in person_names:
        _add_results(store.search_substring(name, limit=50))
    
    # === Pass 4: Multi-hop entity expansion ===
    if results:
        # Extract new entities from top-10 results
        top_text = " ".join(r["text"] for r in results[:10])
        new_ents = extract_entities(top_text)
        
        original_lower = {t.lower() for t in all_terms}
        hop2_terms = []
        for ent_text, ent_label in new_ents:
            if ent_label in ("PERSON", "ORG", "GPE", "LOC", "FAC", "EVENT", "WORK_OF_ART"):
                if ent_text.lower() not in original_lower:
                    hop2_terms.append(ent_text)
        
        if hop2_terms:
            _add_results(store.search_fts(hop2_terms, limit=30))
    
    # === Pass 5: Fallback if very few results ===
    if len(results) < 5:
        # Try each important term individually via substring
        for term, weight in parsed[:5]:
            _add_results(store.search_substring(term, limit=20))
    
    return results[:max_candidates]
