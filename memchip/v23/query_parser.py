"""NER/POS-weighted query parsing (SmartSearch-style)."""
from __future__ import annotations
import spacy

_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# POS weights (SmartSearch paper)
POS_WEIGHTS = {
    "PROPN": 3.0,
    "NOUN": 2.0,
    "VERB": 1.0,
    "ADJ": 1.0,
    "NUM": 2.0,
}
NER_BONUS = 1.0


def parse_query(question: str) -> list[tuple[str, float]]:
    """Parse question into weighted search terms using SpaCy NER/POS.
    
    Returns list of (term, weight) sorted by weight descending.
    """
    nlp = _get_nlp()
    doc = nlp(question)
    
    # Collect NER spans for bonus
    ner_tokens = set()
    entities = []
    for ent in doc.ents:
        entities.append((ent.text, ent.label_))
        for tok in ent:
            ner_tokens.add(tok.i)
    
    # Weight each token
    terms = {}
    for tok in doc:
        if tok.is_stop or tok.is_punct or len(tok.text) <= 1:
            continue
        
        text = tok.text.lower()
        weight = POS_WEIGHTS.get(tok.pos_, 0.5)
        
        # NER bonus
        if tok.i in ner_tokens:
            weight += NER_BONUS
        
        # Keep highest weight for duplicates
        if text not in terms or weight > terms[text]:
            terms[text] = weight
    
    # Also add full entity spans as terms (for multi-word entities)
    for ent_text, ent_label in entities:
        w = 4.0  # High weight for full entity matches
        terms[ent_text.lower()] = w
    
    # Sort by weight descending
    return sorted(terms.items(), key=lambda x: -x[1])


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Extract named entities from text. Returns list of (text, label)."""
    nlp = _get_nlp()
    doc = nlp(text)
    return [(ent.text, ent.label_) for ent in doc.ents]
