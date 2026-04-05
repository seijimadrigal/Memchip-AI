"""Query parser using SpaCy NER/POS tagging for weighted term extraction."""
from __future__ import annotations
import spacy

_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def parse_query(question: str) -> list[tuple[str, float]]:
    """Extract weighted search terms from a question.
    
    Returns list of (term, weight) tuples.
    Weights: proper nouns 3.0, nouns 2.0, verbs 1.0, +1.0 for named entities.
    """
    nlp = _get_nlp()
    doc = nlp(question)
    
    # Collect entity spans for bonus
    ent_texts = {ent.text.lower() for ent in doc.ents}
    ent_tokens = set()
    for ent in doc.ents:
        for tok in ent:
            ent_tokens.add(tok.i)
    
    terms = {}  # term -> weight
    
    # Add full entity names as terms (high weight)
    for ent in doc.ents:
        terms[ent.text] = 4.0  # proper noun (3.0) + entity bonus (1.0)
    
    # Add individual tokens
    for tok in doc:
        if tok.is_stop or tok.is_punct or tok.is_space:
            continue
        if len(tok.text) < 2:
            continue
            
        weight = 0.0
        if tok.pos_ == "PROPN":
            weight = 3.0
        elif tok.pos_ == "NOUN":
            weight = 2.0
        elif tok.pos_ == "VERB" and tok.lemma_ not in {"be", "have", "do", "go", "say", "get", "make", "know", "think", "take", "come", "want", "use"}:
            weight = 1.0
        elif tok.pos_ == "ADJ":
            weight = 0.5
        else:
            continue
        
        # Entity bonus
        if tok.i in ent_tokens:
            weight += 1.0
        
        text = tok.text
        if text in terms:
            terms[text] = max(terms[text], weight)
        else:
            terms[text] = weight
    
    # Sort by weight descending
    result = sorted(terms.items(), key=lambda x: -x[1])
    return result


def get_search_terms(question: str, top_n: int = 10) -> list[str]:
    """Get top N search terms by weight."""
    parsed = parse_query(question)
    return [t for t, w in parsed[:top_n]]
