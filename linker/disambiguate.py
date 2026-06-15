"""Disambiguation: pick a single candidate, or abstain (NIL).

Inputs to disambiguate():
  - candidates_ : the list returned by linker.candidates.candidates()
  - ner_label   : the spaCy NER label of the span (e.g., "ORG", "GPE", "FOOD")
  - doc_resolved: the list of LinkResult records already resolved in this
                  document (in document order). Used for co-occurrence
                  signal — a candidate that connects (1 hop in Cypher) to
                  an already-resolved entity is more likely correct.

Required signals (any subset whose combination cleanly resolves the
candidate set, in priority order):
  (a) Length-1 candidate list -> resolved-unique.
  (b) Type compatibility via NER_LABEL_TO_KG_TYPE -> resolved-by-type
      when exactly one candidate matches the allowed labels.
  (c) Hierarchical type compatibility via [:SUBCLASS_OF*0..] -> e.g.,
      a candidate of label :Cuisine resolves when ner_label is "FOOD"
      because :Cuisine is reachable under the type-compatible umbrella.
      reason token = "resolved-by-hierarchy".
  (d) Co-occurrence with doc_resolved entities via 1-hop Cypher MATCH:
      among the surviving candidates, prefer the one with the highest
      neighbour overlap. reason token = "resolved-by-context".
  (e) None of the above resolve -> (None, "nil-no-candidates") when
      candidates_ is empty, else (None, "nil-ambiguous").

Returns: (chosen_candidate_dict_or_None, reason_token).
"""


# NER label -\u003e set of KG labels that are directly type-compatible.
# Learner extends this table for the full evaluation set; two seed entries
# are provided as exemplars.
NER_LABEL_TO_KG_TYPE: dict[str, set[str]] = {
    "PERSON": {"Author"},
    "ORG": {"Author"},
    "GPE": {"Cuisine"},
    "FOOD": {"Ingredient", "Cuisine"},   # ambiguous on purpose — hierarchy resolves
    "INGREDIENT": {"Ingredient"},
    "TECHNIQUE": {"Technique"},
    "RECIPE": {"Recipe"},
    "MISC": set(),                        # deliberately empty — NIL-ambiguous
}


def disambiguate(
    driver,
    candidates_: list[dict],
    ner_label: str,
    doc_resolved: list,
) -> tuple[dict | None, str]:
    """Return (chosen_candidate_or_None, reason_token).

    See the module docstring for the required signals and reason tokens.

    Implementation guidance:
      - Handle the trivial cases first (empty list, length-1 list).
      - Apply the NER_LABEL_TO_KG_TYPE filter. If exactly one candidate
        survives, return it with reason "resolved-by-type".
      - For the hierarchical case, the load-bearing Cypher shape is:
            MATCH (c:Entity {id: $cand_id})
            MATCH (c)-[:SUBCLASS_OF*0..]->(ancestor:Entity)
            RETURN collect(labels(ancestor)) AS ancestor_labels
        Then check whether ancestor labels intersect the type-compatible
        set. The "*0.." length means the candidate itself counts as a
        depth-0 ancestor, so a direct match resolves here too.
      - For co-occurrence, MATCH a 1-hop neighbourhood from each candidate
        and count how many doc_resolved node ids appear in it. Highest
        count wins; ties fall through to "nil-ambiguous".
    """
    # (a) Empty candidate list
    if not candidates_:
        return (None, "nil-no-candidates")

    # (b) Single candidate — resolved immediately
    if len(candidates_) == 1:
        return (candidates_[0], "resolved-unique")

    # ── Signal 2: type-filter via NER_LABEL_TO_KG_TYPE ──────────────────────
    allowed_types = NER_LABEL_TO_KG_TYPE.get(ner_label, set())
    if allowed_types:
        typed = [c for c in candidates_ if any(lbl in allowed_types for lbl in c["labels"])]
        if len(typed) == 1:
            return (typed[0], "resolved-by-type")
        if typed:
            candidates_ = typed  # narrow the field for later signals

    # ── Signal 3: hierarchical SUBCLASS_OF*0.. traversal ────────────────────
    # For each surviving candidate, traverse its ancestor chain and check
    # whether any ancestor's labels intersect the allowed type set.
    if allowed_types and driver is not None:
        heir_query = (
            "MATCH (c:Entity {id: $cand_id}) "
            "MATCH (c)-[:SUBCLASS_OF*0..]->(ancestor:Entity) "
            "RETURN collect(labels(ancestor)) AS ancestor_labels_list"
        )
        surviving = []
        for cand in candidates_:
            with driver.session() as s:
                row = s.run(heir_query, cand_id=cand["id"]).single()
            if row is None:
                continue
            # ancestor_labels_list is a list-of-lists; flatten and de-dup.
            all_ancestor_labels: set[str] = set()
            for label_list in row["ancestor_labels_list"]:
                all_ancestor_labels.update(label_list)
            all_ancestor_labels.discard("Entity")
            if all_ancestor_labels & allowed_types:
                surviving.append(cand)
        if len(surviving) == 1:
            return (surviving[0], "resolved-by-hierarchy")
        if surviving:
            candidates_ = surviving

    # ── Signal 4: co-occurrence with already-resolved doc entities ───────────
    if doc_resolved and driver is not None:
        resolved_ids = [
            r.predicted_node_id
            for r in doc_resolved
            if r.predicted_node_id is not None
        ]
        if resolved_ids:
            overlap_query = (
                "MATCH (cand:Entity {id: $cand_id})-[*1..1]-(neighbor:Entity) "
                "WHERE neighbor.id IN $resolved_ids "
                "RETURN count(DISTINCT neighbor) AS overlap"
            )
            scores = []
            for cand in candidates_:
                with driver.session() as s:
                    row = s.run(overlap_query, cand_id=cand["id"], resolved_ids=resolved_ids).single()
                overlap = row["overlap"] if row else 0
                scores.append((overlap, cand))
            best_overlap = max(sc for sc, _ in scores)
            if best_overlap > 0:
                winners = [c for sc, c in scores if sc == best_overlap]
                if len(winners) == 1:
                    return (winners[0], "resolved-by-context")

    # ── No signal resolved ───────────────────────────────────────────────────
    return (None, "nil-ambiguous")
