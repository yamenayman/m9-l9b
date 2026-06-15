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
    # 1. Build gold-span index keyed by (doc_id, start, end)
    gold_index: dict[tuple, "GoldSpan"] = {}
    for gs in gold:
        gold_index[(gs.doc_id, gs.start, gs.end)] = gs

    # Collect per-doc counts
    doc_ids = {gs.doc_id for gs in gold}
    per_doc: dict[str, dict[str, int]] = {
        d: {"tp": 0, "fp": 0, "fn": 0} for d in doc_ids
    }

    # 2. Filter predictions to the gold span set and accumulate counts
    pred_index: dict[tuple, "LinkResult"] = {}
    for p in predictions:
        key = (p.doc_id, p.start, p.end)
        if key in gold_index:
            pred_index[key] = p

    for key, gs in gold_index.items():
        pred = pred_index.get(key)
        gold_nil = gs.gold_node_id is None
        pred_nil = pred is None or pred.predicted_node_id is None

        if gold_nil and pred_nil:
            # TN-NIL: not counted in P or R
            continue
        elif gold_nil and not pred_nil:
            # Non-NIL prediction on NIL gold → FP only
            per_doc[gs.doc_id]["fp"] += 1
        elif not gold_nil and pred_nil:
            # NIL prediction on non-NIL gold → FN only
            per_doc[gs.doc_id]["fn"] += 1
        else:
            # Both non-NIL: TP if exact match else FP+FN
            exact = (
                pred.predicted_node_id == gs.gold_node_id
                and pred.predicted_type_label == gs.gold_type_label
            )
            if exact:
                per_doc[gs.doc_id]["tp"] += 1
            else:
                per_doc[gs.doc_id]["fp"] += 1
                per_doc[gs.doc_id]["fn"] += 1

    # 3. Macro-average: compute per-doc P/R/F1, skip docs with no gold spans
    precisions, recalls, f1s = [], [], []
    for doc_id, counts in per_doc.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        # Skip documents with no gold non-NIL spans AND no non-NIL predictions
        # (i.e., nothing to score on this doc)
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        precisions.append(p)
        recalls.append(r)
        f1s.append(f)

    if not precisions:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    return {
        "precision": sum(precisions) / len(precisions),
        "recall": sum(recalls) / len(recalls),
        "f1": sum(f1s) / len(f1s),
    }
