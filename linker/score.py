"""Linker P/R/F1 scoring."""
from linker.types import LinkResult, GoldSpan


def score(predictions: list[LinkResult], gold: list[GoldSpan]) -> dict:
    """Compute precision, recall, F1 over (node_id, type_label) tuples.

    Triple-stated methodology (verbatim in lab-spec.md, lab guide page, and
    this docstring):

    - Predictions are filtered to the gold span set (same doc_id, start, end)
      before scoring; predictions on spans absent from gold are dropped.
    - A span is a true positive iff the predicted (node_id, type_label)
      EXACTLY matches gold AND gold is non-NIL.
    - A prediction of a wrong (node_id, type_label) on a non-NIL gold is a
      false positive AND a false negative on that span.
    - A NIL prediction on a non-NIL gold is a false negative only.
    - A non-NIL prediction on a NIL gold is a false positive only.
    - A NIL prediction on a NIL gold is a true negative (not counted in
      precision or recall).
    - Aggregation is macro-average across documents (per-doc P/R/F1 averaged
      with equal weight per doc; docs with no gold spans are skipped).

    Returns {'precision': float, 'recall': float, 'f1': float}.
    """
    # TODO:
    # 1. Build a gold-span index keyed by (doc_id, start, end) for fast lookup.
    # 2. Filter predictions to the gold span set per the methodology.
    # 3. For each doc_id in gold, accumulate TP / FP / FN per the rules above
    #    (TN-NIL is informational only — not in P or R).
    # 4. Compute per-doc P, R, F1 (with 0/0 convention: P=R=F1=0 when the
    #    denominator is 0; skip docs with no gold spans entirely).
    # 5. Macro-average the per-doc metrics; return the dict.
    raise NotImplementedError(
        "score() is not yet implemented — implement the triple-stated "
        "methodology described in this docstring."
    )
