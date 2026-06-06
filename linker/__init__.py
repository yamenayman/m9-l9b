"""Entity-linking module for Lab 9B.

Public surface (imported by the Integration repo):
  - link(driver, doc_id, text, ner_spans) -> list[LinkResult]
  - score(predictions, gold) -> dict

See linker/types.py for the LinkResult and GoldSpan dataclasses.
"""
from linker.types import LinkResult, GoldSpan
from linker.identity import canonical_id
from linker.candidates import candidates
from linker.disambiguate import disambiguate, NER_LABEL_TO_KG_TYPE
from linker.link import link
from linker.score import score

__all__ = [
    "LinkResult",
    "GoldSpan",
    "canonical_id",
    "candidates",
    "disambiguate",
    "NER_LABEL_TO_KG_TYPE",
    "link",
    "score",
]
