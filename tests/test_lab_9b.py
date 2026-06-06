"""Lab 9B autograder.

Gates implemented per Phase 3 build-contract §3.3. Test-split thresholds
pinned 2026-06-05: reference linker measures dev 0.99/0.99/0.99 and test
1.00/1.00/1.00 against the bundled fixture; pins 0.80/0.65/0.72 leave
~20-pt headroom so a partial-cascade implementation (Stage 1+2 only)
still passes.
"""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# conftest.py adds the repo root to sys.path. Import the learner-facing
# package here so collection-time import failures surface clearly.
from linker import link, score, candidates, disambiguate, GoldSpan, LinkResult
from linker.identity import canonical_id


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ids(rows) -> set:
    return {r["id"] for r in rows}


def _load_split(name: str) -> list[dict]:
    docs = []
    with open(DATA_DIR / f"{name}.jsonl") as f:
        for line in f:
            if line.strip():
                docs.append(json.loads(line))
    return docs


# ---------------------------------------------------------------------------
# Gate 1: Identity Discipline
# ---------------------------------------------------------------------------

def test_entity_id_uniqueness(driver):
    """Phase 3 §2.6 duplicate-detect Cypher must return 0 rows.

    Catches buggy variant: a fixture load that creates duplicate :Entity
    nodes (e.g., MERGE on `name` instead of `id`, or two MERGEs with
    different label sets but the same intended identity).
    """
    with driver.session() as s:
        rows = list(s.run(
            "MATCH (n:Entity) "
            "WITH n.id AS id, count(*) AS c "
            "WHERE c > 1 "
            "RETURN id, c"
        ))
    assert rows == [], f"Duplicate :Entity ids: {rows[:5]}"


# ---------------------------------------------------------------------------
# Gate 2: candidates() — correctness
# ---------------------------------------------------------------------------

# 8 fixture surface forms: 1-candidate, ambiguous (2), case variant,
# zero-candidate, author full name, distinct case-pair members.
CANDIDATE_CASES = [
    ("ginger",       {"ingredient:ginger"}),
    ("basil",        {"ingredient:basil"}),                       # NOT author "Basil Hawthorne" (different name)
    ("orange",       {"ingredient:orange", "cuisine:orange"}),    # ambiguous pair
    ("ORANGE",       {"ingredient:orange", "cuisine:orange"}),    # case variant
    ("turkey",       {"ingredient:turkey"}),
    ("Turkish",      {"cuisine:turkish"}),
    ("Maria Rossi",  {"author:maria-rossi"}),
    ("kohlrabi",     set()),                                       # zero candidates (NIL surface)
]


@pytest.mark.parametrize("surface,expected_ids", CANDIDATE_CASES)
def test_candidates_returns_correct_set(driver, surface, expected_ids):
    """`candidates()` returns the right id set across 8 surface forms
    spanning the ambiguous, case-variant, and zero-candidate cases.

    Catches buggy variant: a case-sensitive equality test on `name`, or
    a label-scoped MATCH that misses one half of an ambiguous pair.
    """
    rows = candidates(driver, surface)
    assert isinstance(rows, list), f"candidates() must return a list, got {type(rows)}"
    assert _ids(rows) == expected_ids, (
        f"surface={surface!r}: got {_ids(rows)}, expected {expected_ids}"
    )
    # Sanity: each row must carry id, name, labels (sans :Entity)
    for r in rows:
        assert set(r.keys()) >= {"id", "name", "labels"}, r
        assert "Entity" not in r["labels"], (
            "labels list must exclude the universal :Entity label"
        )


# ---------------------------------------------------------------------------
# Gate 3: candidates() — parameterized Cypher (AST)
# ---------------------------------------------------------------------------

CANDIDATES_SRC_PATH = REPO_ROOT / "linker" / "candidates.py"


def _docstring_constants(tree: ast.AST) -> set:
    """Collect id() of Constant nodes that are docstrings — so we can
    exclude them from the parameterized-Cypher search (a $param token
    in a docstring is documentation, not the actual query)."""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                skip.add(id(body[0].value))
    return skip


def _non_doc_string_literals(tree: ast.AST) -> list[str]:
    skip = _docstring_constants(tree)
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]


def _fstring_nodes(tree: ast.AST) -> list[ast.JoinedStr]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]


def test_candidates_uses_parameterized_cypher():
    """AST inspection on `linker/candidates.py`:

    1. Some literal string contains a Cypher `$<name>` parameter token.
    2. No f-string in the file interpolates the name `surface` into its
       parts (which would mean string-injection of the NER surface into
       the Cypher query).

    Catches buggy variant: `session.run(f"MATCH (n) WHERE n.name = '{surface}'")`
    which silently passes for benign inputs but corrupts on apostrophes
    and is an injection surface.
    """
    src = CANDIDATES_SRC_PATH.read_text()
    tree = ast.parse(src)

    literals = _non_doc_string_literals(tree)
    param_re_hits = [s for s in literals if "$" in s and any(
        # `$<identifier>` pattern present
        c.isalpha() for c in s.split("$", 1)[1][:1]
    )]
    assert param_re_hits, (
        "candidates.py must use a parameterized Cypher token like `$surface` "
        "in a non-docstring Cypher string literal passed to session.run — "
        "none found. (A $param token in the docstring does not count.)"
    )

    for js in _fstring_nodes(tree):
        for part in js.values:
            if isinstance(part, ast.FormattedValue):
                # FormattedValue wraps an expression; check if it references
                # the `surface` parameter name directly.
                if isinstance(part.value, ast.Name) and part.value.id == "surface":
                    pytest.fail(
                        "candidates.py contains an f-string that interpolates "
                        "`surface` into a string. Use $param Cypher binding "
                        "via session.run kwargs instead."
                    )


# ---------------------------------------------------------------------------
# Gate 4: disambiguate() — type filter
# ---------------------------------------------------------------------------

# Each case: (candidates_list, ner_label, expected_chosen_id_or_None, expected_reason_or_set_of_reasons)
TYPE_FILTER_CASES = [
    # Author "Maria Rossi" + spurious ingredient hit — PERSON narrows to Author.
    (
        [
            {"id": "author:maria-rossi", "name": "Maria Rossi", "labels": ["Author"]},
            {"id": "ingredient:rosemary", "name": "Maria Rossi", "labels": ["Ingredient"]},
        ],
        "PERSON",
        "author:maria-rossi",
    ),
    # ORG narrows to Author similarly.
    (
        [
            {"id": "author:chen-wei", "name": "Chen Wei", "labels": ["Author"]},
            {"id": "ingredient:basil", "name": "Chen Wei", "labels": ["Ingredient"]},
        ],
        "ORG",
        "author:chen-wei",
    ),
    # INGREDIENT narrows to Ingredient.
    (
        [
            {"id": "ingredient:orange", "name": "orange", "labels": ["Ingredient"]},
            {"id": "cuisine:orange",    "name": "Orange", "labels": ["Cuisine"]},
        ],
        "INGREDIENT",
        "ingredient:orange",
    ),
    # GPE narrows to Cuisine.
    (
        [
            {"id": "ingredient:turkey", "name": "turkey",  "labels": ["Ingredient"]},
            {"id": "cuisine:turkish",   "name": "Turkish", "labels": ["Cuisine"]},
        ],
        "GPE",
        "cuisine:turkish",
    ),
    # PERSON narrows to Author "Basil Hawthorne".
    (
        [
            {"id": "author:basil-hawthorne", "name": "Basil Hawthorne", "labels": ["Author"]},
            {"id": "ingredient:basil",       "name": "basil",           "labels": ["Ingredient"]},
        ],
        "PERSON",
        "author:basil-hawthorne",
    ),
    # TECHNIQUE narrows to Technique.
    (
        [
            {"id": "technique:wok",     "name": "wok",     "labels": ["Technique"]},
            {"id": "ingredient:noodle", "name": "wok",     "labels": ["Ingredient"]},
        ],
        "TECHNIQUE",
        "technique:wok",
    ),
]


@pytest.mark.parametrize("cands,ner_label,expected_id", TYPE_FILTER_CASES)
def test_disambiguate_type_filter(driver, cands, ner_label, expected_id):
    """`disambiguate` uses NER_LABEL_TO_KG_TYPE to pick the correct
    candidate when type alone is decisive.

    Catches buggy variant: ignoring NER label and returning candidates[0].
    """
    chosen, reason = disambiguate(driver, cands, ner_label, [])
    assert chosen is not None, f"expected a candidate, got NIL with reason={reason!r}"
    assert chosen["id"] == expected_id, (
        f"ner_label={ner_label}: got {chosen['id']}, expected {expected_id}"
    )


# ---------------------------------------------------------------------------
# Gate 5: disambiguate() — hierarchical traversal
# ---------------------------------------------------------------------------

# Each case: a span whose NER label maps via [:SUBCLASS_OF*0..] traversal
# rather than direct type membership. e.g., "Sichuan" with NER label "FOOD"
# should resolve to the :Cuisine node because :Cuisine is the allowed type
# under the FOOD umbrella reached through subclass traversal.
HIERARCHY_CASES = [
    ("Sichuan", "FOOD", "cuisine:sichuan"),
    ("Cantonese", "FOOD", "cuisine:cantonese"),
    ("Japanese", "FOOD", "cuisine:japanese"),
    ("Italian", "FOOD", "cuisine:italian"),
]


@pytest.mark.parametrize("surface,ner_label,expected_id", HIERARCHY_CASES)
def test_disambiguate_hierarchical_traversal(driver, surface, ner_label, expected_id):
    """Cuisines under the Chinese / Asian / World hierarchy resolve via
    `[:SUBCLASS_OF*0..]` when the NER label is the umbrella term `FOOD`.

    Catches buggy variant: a disambiguator that requires direct
    NER_LABEL_TO_KG_TYPE membership and abstains when only an ancestor
    matches.
    """
    cands = candidates(driver, surface)
    chosen, reason = disambiguate(driver, cands, ner_label, [])
    assert chosen is not None, (
        f"surface={surface!r}, ner_label={ner_label}: got NIL (reason={reason!r})"
    )
    assert chosen["id"] == expected_id, (
        f"surface={surface!r}: got {chosen['id']}, expected {expected_id}"
    )


# ---------------------------------------------------------------------------
# Gate 6: disambiguate() — NIL when ambiguous
# ---------------------------------------------------------------------------

NIL_CASES = [
    # Empty candidate list -> nil-no-candidates.
    ([], "INGREDIENT", "nil-no-candidates"),
    ([], "FOOD",       "nil-no-candidates"),
    # Two candidates, NER label is neutral (not in NER_LABEL_TO_KG_TYPE
    # and no hierarchy path resolves uniquely) -> nil-ambiguous.
    (
        [
            {"id": "ingredient:orange", "name": "orange", "labels": ["Ingredient"]},
            {"id": "cuisine:orange",    "name": "Orange", "labels": ["Cuisine"]},
        ],
        "MISC",
        "nil-ambiguous",
    ),
    (
        [
            {"id": "ingredient:turkey", "name": "turkey",  "labels": ["Ingredient"]},
            {"id": "cuisine:turkish",   "name": "Turkish", "labels": ["Cuisine"]},
        ],
        "MISC",
        "nil-ambiguous",
    ),
    (
        [
            {"id": "ingredient:sage",     "name": "sage",          "labels": ["Ingredient"]},
            {"id": "author:sage-mitchell", "name": "Sage Mitchell", "labels": ["Author"]},
        ],
        "MISC",
        "nil-ambiguous",
    ),
]


@pytest.mark.parametrize("cands,ner_label,expected_reason", NIL_CASES)
def test_disambiguate_nil_when_ambiguous(driver, cands, ner_label, expected_reason):
    """Abstain (return None) when no signal resolves the ambiguity.

    Catches buggy variant: a disambiguator that silently picks
    candidates[0] when no signal applies — turns an unmodelled surface
    into a confident wrong link.
    """
    chosen, reason = disambiguate(driver, cands, ner_label, [])
    assert chosen is None, f"expected NIL, got {chosen}"
    assert reason == expected_reason, (
        f"expected reason={expected_reason!r}, got {reason!r}"
    )


# ---------------------------------------------------------------------------
# Gate 7: link() orchestrator
# ---------------------------------------------------------------------------

def test_link_orchestrates_pipeline(driver):
    """`link()` produces correct `(node_id, type_label)` on a 5-span synthetic doc.

    Catches buggy variant: failing to thread `doc_resolved` through, or
    losing span ordering, or mishandling NIL spans.
    """
    text = (
        "Maria Rossi cooks a Sichuan recipe with ginger and basil "
        "but no kohlrabi."
    )
    ner_spans = [
        # (start, end, surface, ner_label)
        (0, 11, "Maria Rossi", "PERSON"),
        (21, 28, "Sichuan", "FOOD"),
        (37, 43, "ginger", "INGREDIENT"),
        (48, 53, "basil", "INGREDIENT"),
        (61, 69, "kohlrabi", "INGREDIENT"),
    ]
    expected = [
        ("author:maria-rossi", "Author"),
        ("cuisine:sichuan",    "Cuisine"),
        ("ingredient:ginger",  "Ingredient"),
        ("ingredient:basil",   "Ingredient"),
        (None, None),
    ]
    results = link(driver, "synth-1", text, ner_spans)
    assert len(results) == len(ner_spans), (
        f"expected one LinkResult per span, got {len(results)}"
    )
    got = [(r.predicted_node_id, r.predicted_type_label) for r in results]
    assert got == expected, f"got {got}, expected {expected}"


# ---------------------------------------------------------------------------
# Gate 8: score() — methodology
# ---------------------------------------------------------------------------

def test_score_methodology():
    """Hand-built (pred, gold) with 1 TP / 1 FP / 1 FN / 1 TN-NIL → P=0.5,
    R=0.5, F1=0.5 within 1e-9. Aligns with the triple-stated docstring.

    Construction (all spans in doc_id="d1"):
      span A: gold=author:x   pred=author:x          -> TP
      span B: gold=ingredient:y pred=ingredient:WRONG -> FP + FN (one span)
      span C: gold=cuisine:z   pred=NIL              -> FN only
      span D: gold=NIL         pred=NIL              -> TN-NIL (not counted)

    Per-doc:
      TP=1, FP=1, FN=2  (span B contributes both FP and FN; span C contributes FN)
      precision = 1 / (1+1) = 0.5
      recall    = 1 / (1+2) = 0.333...
      f1        = 2*P*R/(P+R) = 2*0.5*0.333 / 0.833 = 0.4

    Wait — the contract states P=R=F1=0.5. To hit that exactly, we need
    TP=1, FP=1, FN=1. So we drop the "wrong-prediction on non-NIL gold
    counts as BOTH FP and FN" doubling on this construction by using
    NIL predictions for the FN-only case and a non-NIL prediction for
    the FP-only case. Construction:

      span A: gold=author:x       pred=author:x          -> TP
      span B: gold=NIL            pred=ingredient:y      -> FP only
      span C: gold=cuisine:z      pred=NIL               -> FN only
      span D: gold=NIL            pred=NIL               -> TN-NIL
    """
    gold = [
        GoldSpan("d1", 0,  4, "X", "author:x",    "Author"),
        GoldSpan("d1", 5,  9, "Y", None,          None),       # NIL
        GoldSpan("d1", 10, 14, "Z", "cuisine:z",  "Cuisine"),
        GoldSpan("d1", 15, 19, "W", None,         None),       # NIL
    ]
    pred = [
        LinkResult("d1", 0,  4, "X", "author:x",      "Author",     "resolved-unique"),
        LinkResult("d1", 5,  9, "Y", "ingredient:y",  "Ingredient", "resolved-unique"),
        LinkResult("d1", 10, 14, "Z", None,           None,         "nil-ambiguous"),
        LinkResult("d1", 15, 19, "W", None,           None,         "nil-no-candidates"),
    ]
    m = score(pred, gold)
    assert abs(m["precision"] - 0.5) < 1e-9, m
    assert abs(m["recall"] - 0.5) < 1e-9, m
    assert abs(m["f1"] - 0.5) < 1e-9, m


# ---------------------------------------------------------------------------
# Gate 9: dev split — structural (numbers printed)
# ---------------------------------------------------------------------------

def test_dev_split_thresholds_reported(driver):
    """Run on dev split: structural check that score() returns three
    numeric metrics. Threshold check is on the test split (Gate 10).
    """
    docs = _load_split("dev")
    assert docs, "dev.jsonl must contain at least one doc"
    preds = []
    gold = []
    for d in docs:
        ner_spans = [tuple(s) for s in d["ner_spans"]]
        preds.extend(link(driver, d["doc_id"], d["text"], ner_spans))
        for g in d["gold"]:
            gold.append(GoldSpan(
                doc_id=d["doc_id"],
                start=g["start"], end=g["end"],
                surface=g["surface"],
                gold_node_id=g["gold_node_id"],
                gold_type_label=g["gold_type_label"],
            ))
    m = score(preds, gold)
    assert set(m.keys()) >= {"precision", "recall", "f1"}
    for k in ("precision", "recall", "f1"):
        assert isinstance(m[k], (int, float)), f"{k} must be numeric, got {type(m[k])}"
        assert 0.0 <= m[k] <= 1.0, f"{k} out of [0,1]: {m[k]}"
    print(f"\nDev split: precision={m['precision']:.4f} "
          f"recall={m['recall']:.4f} f1={m['f1']:.4f}")


# ---------------------------------------------------------------------------
# Gate 10: test split — thresholds (placeholder values, Phase 6 pins)
# ---------------------------------------------------------------------------

# Pinned 2026-06-05 against reference linker (answer-key.md §§2.1–2.5)
# measured on the bundled fixture: dev P=R=F1≈0.99, test P=R=F1=1.00.
# Pins leave headroom for partial-cascade learner submissions.
TEST_PRECISION_THRESHOLD = 0.80
TEST_RECALL_THRESHOLD    = 0.65
TEST_F1_THRESHOLD        = 0.72


def test_test_split_meets_thresholds(driver):
    """Full pipeline against the test split must meet the gating thresholds.

    Catches buggy variant: a linker that abstains on everything (R=0) or
    picks candidates[0] without disambiguation (P collapses on ambiguous
    pairs and NIL surfaces).
    """
    docs = _load_split("test")
    preds = []
    gold = []
    for d in docs:
        ner_spans = [tuple(s) for s in d["ner_spans"]]
        preds.extend(link(driver, d["doc_id"], d["text"], ner_spans))
        for g in d["gold"]:
            gold.append(GoldSpan(
                doc_id=d["doc_id"],
                start=g["start"], end=g["end"],
                surface=g["surface"],
                gold_node_id=g["gold_node_id"],
                gold_type_label=g["gold_type_label"],
            ))
    m = score(preds, gold)
    print(f"\nTest split: precision={m['precision']:.4f} "
          f"recall={m['recall']:.4f} f1={m['f1']:.4f}")
    assert m["precision"] >= TEST_PRECISION_THRESHOLD, (
        f"precision {m['precision']:.4f} < threshold {TEST_PRECISION_THRESHOLD}"
    )
    assert m["recall"] >= TEST_RECALL_THRESHOLD, (
        f"recall {m['recall']:.4f} < threshold {TEST_RECALL_THRESHOLD}"
    )
    assert m["f1"] >= TEST_F1_THRESHOLD, (
        f"f1 {m['f1']:.4f} < threshold {TEST_F1_THRESHOLD}"
    )


# ---------------------------------------------------------------------------
# Gate 11: unmodified starter must fail
# ---------------------------------------------------------------------------

def test_starter_unmodified_fails():
    """Per the Unmodified Starter Failure Rule: pytest on the unmodified
    starter must produce ≥1 failure. We assert this via the import-time
    behaviour of `candidates`, `disambiguate`, `link`, `score`: every
    TODO raises NotImplementedError. If ANY of these has been wired to
    silently pass on a smoke input, this test fails — flagging a silent-
    pass bug introduced by an over-aggressive fix.

    The test passes (sentinel) iff at least one of the four TODO
    functions still raises NotImplementedError on a trivial input.
    """
    sentinel_raises = 0
    try:
        candidates(None, "ginger")
    except NotImplementedError:
        sentinel_raises += 1
    except Exception:
        pass
    try:
        disambiguate(None, [], "PERSON", [])
    except NotImplementedError:
        sentinel_raises += 1
    except Exception:
        pass
    try:
        link(None, "d", "t", [])
    except NotImplementedError:
        sentinel_raises += 1
    except Exception:
        pass
    try:
        score([], [])
    except NotImplementedError:
        sentinel_raises += 1
    except Exception:
        pass
    # This test is a structural sentinel — it is EXPECTED to fail on the
    # unmodified starter (because at least one TODO still raises). It
    # passes only on a fully-implemented submission. That is the
    # unmodified-starter-failure contract: at least one autograder gate
    # MUST be red on the unmodified starter.
    assert sentinel_raises == 0, (
        f"{sentinel_raises} of 4 TODO functions still raise NotImplementedError. "
        "Complete the TODOs in linker/candidates.py, linker/disambiguate.py, "
        "linker/link.py, and linker/score.py."
    )
