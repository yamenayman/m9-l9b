# Module 9 Week B — Applied Lab: Entity Linking

Build an entity-linking module that takes spaCy NER spans over recipe-blog
text plus a pre-loaded recipe property graph in Neo4j, returns one
`LinkResult` per span (`(node_id, type_label)` or NIL), and reports
precision / recall / F1 against a gold set.

The module exposes a clean function-call API (`link(driver, doc_id, text, ner_spans)
-> list[LinkResult]`) so the Week B integration repo can import it without
modification.

## What you build

| File | Status | Your work |
|---|---|---|
| `linker/types.py` | complete | — |
| `linker/identity.py` | partial | `merge_entity` TODO (Identity Mapping helper) |
| `linker/candidates.py` | TODO | parameterized Cypher candidate generation |
| `linker/disambiguate.py` | TODO | type filter + hierarchical `[:SUBCLASS_OF*0..]` + co-occurrence |
| `linker/link.py` | TODO | orchestrator |
| `linker/score.py` | TODO | triple-stated P/R/F1 |

## Setup

1. **Fork this repo and clone your fork.** See [FORK-SUBMIT.md](FORK-SUBMIT.md).
2. **Start Neo4j:**
   ```bash
   docker compose up -d
   docker compose logs -f neo4j | grep -m1 Started
   ```
3. **Install dependencies and the spaCy model:**
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```
4. **Load the fixture KG:**
   ```bash
   python load_fixture.py
   ```
   Expected output ends with `OK: fixture loaded, counts within tolerance, identity unique.`

## Run the autograder locally

```bash
pytest tests/ -v
```

Tests are stage-gated. The unit-style tests (`test_candidates_*`, `test_disambiguate_*`,
`test_score_methodology`) will start passing as you complete the corresponding
TODOs. The integration tests (`test_link_orchestrates_pipeline`,
`test_test_split_meets_thresholds`) require all four TODOs implemented.

The `test_test_split_meets_thresholds` gate enforces P ≥ 0.80, R ≥ 0.65,
F1 ≥ 0.72 on the bundled test split. The reference linker measures
~1.00 on this split, so the gate is calibrated to pass a partial-cascade
implementation (Stage 1+2 only) while catching a broken linker.

## Iterate on dev

```bash
python run_dev_eval.py
```

Prints precision / recall / F1 on the dev split (20 docs). Use it to
tune your disambiguation strategy before the autograder evaluates against
the test split (which you do not see until you submit).

## Grading methodology — Precision / Recall / F1

This is the methodology the autograder uses, stated identically in the
lab specification, the published Applied Lab guide, and the `score()`
docstring:

- Predictions are filtered to the gold span set (same `doc_id, start, end`)
  before scoring; predictions on spans absent from gold are dropped.
- A span is a true positive iff the predicted `(node_id, type_label)`
  EXACTLY matches gold AND gold is non-NIL.
- A prediction of a wrong `(node_id, type_label)` on a non-NIL gold is a
  false positive AND a false negative on that span.
- A NIL prediction on a non-NIL gold is a false negative only.
- A non-NIL prediction on a NIL gold is a false positive only.
- A NIL prediction on a NIL gold is a true negative (not counted in
  precision or recall).
- Aggregation is macro-average across documents (per-doc P/R/F1 averaged
  with equal weight per doc; docs with no gold spans are skipped).

## Submit

When CI passes on a PR against your fork, paste the PR URL into
TalentLMS → Module 9 Week B → Applied Lab. See
[FORK-SUBMIT.md](FORK-SUBMIT.md) for the full submission flow.

---

## License

This repository is provided for educational use only. See [LICENSE](LICENSE) for terms.

You may clone and modify this repository for personal learning and practice, and reference code you wrote here in your professional portfolio. Redistribution outside this course is not permitted.
