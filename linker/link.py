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
    # TODO:
    # 1. Initialize results = [] and doc_resolved = [].
    # 2. For each (start, end, surface, ner_label) in ner_spans (in order):
    #      a. Call candidates(driver, surface).
    #      b. Call disambiguate(driver, candidates_list, ner_label, doc_resolved).
    #      c. Construct a LinkResult (predicted_node_id/predicted_type_label
    #         from the chosen candidate dict, or None on NIL).
    #      d. Append it to results AND to doc_resolved.
    # 3. Return results.
    raise NotImplementedError(
        "link() is not yet implemented — orchestrate candidates -> disambiguate "
        "per the Lab guide."
    )
