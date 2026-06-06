# Lab 9B — Data

The fixture KG and labelled splits in this directory are all produced
deterministically by `_build_fixture.py` (seed `9020`). They are
committed so CI does not need to regenerate them; the generator is
shipped only for transparency and to support fixture rebuilds during
curriculum maintenance.

## Files

| File | Purpose |
|---|---|
| `recipes_kg.cypher` | ~200-node recipe KG. Loaded by `load_fixture.py` at the start of every CI run. |
| `train.jsonl` | 80 docs, ~484 gold spans. Intended for design intuition only — the autograder does not use it. |
| `dev.jsonl` | 20 docs, ~126 gold spans. `run_dev_eval.py` reports dev P/R/F1 for tuning. |
| `test.jsonl` | 20 docs, ~127 gold spans. The autograder gates on test-split thresholds. |
| `_build_fixture.py` | Generator. Do not invoke during normal lab work. |

## Document format

One JSON object per line. Schema:

```json
{
  "doc_id": "dev-0007",
  "text": "This italian recipe by ...",
  "ner_spans": [
    [22, 33, "Maria Rossi", "PERSON"]
  ],
  "gold": [
    {
      "start": 22,
      "end": 33,
      "surface": "Maria Rossi",
      "gold_node_id": "author:maria-rossi",
      "gold_type_label": "Author"
    }
  ]
}
```

`gold_node_id` is `null` when the surface form is NIL (no candidate in
the KG).

## Ambiguity and NIL ratios

The generator targets the Phase 3 contract §2.5 ratios across the
dev + test splits:

- ~18% of gold spans are deliberately ambiguous surface forms — pairs
  like `("orange" → ingredient)` vs `("Orange" → cuisine)`, where
  identity discipline + NER label + hierarchy traversal are all
  necessary to disambiguate.
- ~7% of gold spans are NIL — surface forms with no candidate in the
  fixture (e.g., `"kohlrabi"`, `"yuzu"`, `"Bhutanese"`). The linker
  must abstain rather than guess.
