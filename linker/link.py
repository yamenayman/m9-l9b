"""Linker orchestrator.

Wires candidates() -> disambiguate() into one pass over the NER spans of
a document, producing one LinkResult per span.
"""
from linker.candidates import candidates
from linker.disambiguate import disambiguate
from linker.types import LinkResult


def link(
    driver,
    doc_id: str,
    text: str,
    ner_spans: list[tuple[int, int, str, str]],
) -> list[LinkResult]:
    """Orchestrate the linker pipeline for one document.

    Args:
      driver: an open neo4j.GraphDatabase driver.
      doc_id: identifier of this document (propagated into every LinkResult).
      text: the document text (currently unused inside the function; reserved
        for future context features — keep the parameter in the signature
        because the Integration repo calls link() with it).
      ner_spans: a list of (start, end, surface, ner_label) tuples in
        document order.

    Returns: list[LinkResult], one per input span, in the same order.

    Iterate in document order so that doc_resolved grows monotonically and
    the co-occurrence signal builds up as the document is walked.
    """
    results: list[LinkResult] = []
    doc_resolved: list[LinkResult] = []
    for (start, end, surface, ner_label) in ner_spans:
        cands = candidates(driver, surface)
        chosen, reason = disambiguate(driver, cands, ner_label, doc_resolved)
        if chosen is not None:
            node_id = chosen["id"]
            # Pick the first non-Entity label as the type label.
            type_label = chosen["labels"][0] if chosen["labels"] else None
        else:
            node_id = None
            type_label = None
        lr = LinkResult(
            doc_id=doc_id,
            start=start,
            end=end,
            surface=surface,
            predicted_node_id=node_id,
            predicted_type_label=type_label,
            reason=reason,
        )
        results.append(lr)
        doc_resolved.append(lr)
    return results
