"""Deterministic fixture generator for Lab 9B.

Produces:
  - recipes_kg.cypher  : ~200-node MERGE-based fixture matching the
                         Phase 3 build-contract §2.4 count targets.
  - train.jsonl        :  80 docs (~480 gold spans)
  - dev.jsonl          :  20 docs (~120 gold spans)
  - test.jsonl         :  20 docs (~120 gold spans)

Run from `starter/data/`:
    python _build_fixture.py

The generator uses a fixed seed (9020) so its outputs are reproducible.
The .cypher and .jsonl files are committed to the repo, so CI does not
need to regenerate them — the generator is shipped only for transparency
and to support fixture rebuilds during curriculum maintenance.
"""
import json
import random
import re
from pathlib import Path

SEED = 9020
HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Schema literals (match Phase 3 contract §2.1 / §2.3)
# ---------------------------------------------------------------------------

CUISINE_HIERARCHY = [
    ("World", None),
    ("Asian", "World"),
    ("Chinese", "Asian"),
    ("Sichuan", "Chinese"),
    ("Cantonese", "Chinese"),
    ("Hunan", "Chinese"),
    ("Japanese", "Asian"),
    ("Indian", "Asian"),
    ("Thai", "Asian"),
    ("European", "World"),
    ("Italian", "European"),
    ("Tuscan", "Italian"),
    ("Sicilian", "Italian"),
    ("French", "European"),
    ("Spanish", "European"),
    ("Americas", "World"),
    ("Mexican", "Americas"),
    ("NorthAmerican", "Americas"),
]
# That is 18 nodes. Contract calls for 16 cuisines. Trim two leaf
# generals so the count lands on 16 exactly while preserving the
# 3-4 level hierarchy depth (World -> Asian -> Chinese -> Sichuan).
CUISINE_DROP = {"Hunan", "Spanish"}
CUISINE_HIERARCHY = [(n, p) for (n, p) in CUISINE_HIERARCHY if n not in CUISINE_DROP]
assert len(CUISINE_HIERARCHY) == 16, len(CUISINE_HIERARCHY)

# Ingredients (40 total). Eight of them participate in a SUBCLASS_OF chain
# so :Ingredient has the 3-level hierarchy mentioned in §2.2.
INGREDIENTS = [
    # (name, category, parent_or_None)
    ("ginger", "spice", None),
    ("garlic", "vegetable", None),
    ("onion", "vegetable", None),
    ("scallion", "vegetable", "onion"),
    ("shallot", "vegetable", "onion"),
    ("tomato", "vegetable", None),
    ("eggplant", "vegetable", None),
    ("zucchini", "vegetable", None),
    ("basil", "herb", None),  # ambiguous with Author "Basil ..."
    ("sage", "herb", None),   # ambiguous with Author "Sage ..."
    ("oregano", "herb", None),
    ("thyme", "herb", None),
    ("rosemary", "herb", None),
    ("parsley", "herb", None),
    ("cilantro", "herb", None),
    ("mint", "herb", None),
    ("cinnamon", "spice", None),
    ("cumin", "spice", None),
    ("paprika", "spice", None),
    ("turmeric", "spice", None),
    ("peppercorn", "spice", None),
    ("szechuanPeppercorn", "spice", "peppercorn"),
    ("blackPeppercorn", "spice", "peppercorn"),
    ("whitePeppercorn", "spice", "peppercorn"),
    ("chili", "spice", None),
    ("birdsEyeChili", "spice", "chili"),
    ("jalapeno", "spice", "chili"),
    ("rice", "grain", None),
    ("noodle", "grain", None),
    ("pasta", "grain", None),
    ("flour", "grain", None),
    ("chicken", "protein", None),
    ("beef", "protein", None),
    ("pork", "protein", None),
    ("tofu", "protein", None),
    ("turkey", "protein", None),  # ambiguous with Cuisine "Turkish"
    ("shrimp", "protein", None),
    ("orange", "fruit", None),    # ambiguous with Cuisine "Orange"
    ("lemon", "fruit", None),
    ("apple", "fruit", None),
]
assert len(INGREDIENTS) == 40, len(INGREDIENTS)
# Eight SUBCLASS_OF edges: scallion, shallot, szechuanPeppercorn,
# blackPeppercorn, whitePeppercorn, birdsEyeChili, jalapeno = 7. Add one.
# Add: ("rice" parent for noodle? No — keep semantic clean.) Use grain
# chain: tagliatelle->pasta. Add tagliatelle:
INGREDIENTS.append(("tagliatelle", "grain", "pasta"))
assert len(INGREDIENTS) == 41
# Drop "mint" to land exactly at 40.
INGREDIENTS = [t for t in INGREDIENTS if t[0] != "mint"]
assert len(INGREDIENTS) == 40
ingredient_parents = [(n, p) for (n, _c, p) in INGREDIENTS if p]
assert len(ingredient_parents) == 8, len(ingredient_parents)

AUTHORS = [
    ("Maria Rossi", "Italy"),
    ("Chen Wei", "China"),
    ("Sage Mitchell", "USA"),       # ambiguous with ingredient "sage"
    ("Basil Hawthorne", "UK"),      # ambiguous with ingredient "basil"
    ("Hiroshi Tanaka", "Japan"),
    ("Priya Sharma", "India"),
    ("Ananya Kumar", "India"),
    ("Jean Dupont", "France"),
    ("Carmen Vargas", "Mexico"),
    ("Anna Schmidt", "Germany"),
    ("Tom Anderson", "USA"),
    ("Wei Lin", "China"),
]
assert len(AUTHORS) == 12

TECHNIQUES = [
    "wok",
    "braise",
    "roast",
    "grill",
    "steam",
    "boil",
    "fry",
    "saute",
    "bake",
    "stew",
    "smoke",
    "ferment",
]
assert len(TECHNIQUES) == 12

# Add Cuisine ambiguity entries — these are :Cuisine nodes with names that
# collide with ingredient/protein names. They are extra cuisine nodes ON
# TOP of the 16-node hierarchy so contract §2.4 says 16 cuisines exactly.
# So we replace two of the leaf hierarchy nodes with the ambiguity-carrying
# names. Use "Orange" (collides with ingredient "orange") and "Turkish"
# (collides with ingredient "turkey").
# Map: replace "Tuscan" with "Orange" (still child of Italian — semantics
# diverge but the test only cares about disambiguation), and "Sicilian"
# with "Turkish".
CUISINE_RENAMES = {"Tuscan": "Orange", "Sicilian": "Turkish"}
CUISINE_HIERARCHY = [
    (CUISINE_RENAMES.get(n, n), p) for (n, p) in CUISINE_HIERARCHY
]


# ---------------------------------------------------------------------------
# Identity helpers (mirror linker.identity.canonical_id)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")

def slug(name: str) -> str:
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")

def cid(label: str, name: str) -> str:
    return f"{label.lower()}:{slug(name)}"


# ---------------------------------------------------------------------------
# Cypher fixture emission
# ---------------------------------------------------------------------------

def build_cypher(rng: random.Random) -> tuple[str, dict]:
    """Build the recipes_kg.cypher text and a summary dict of counts."""
    lines: list[str] = []

    # Header
    lines.append("// Auto-generated by _build_fixture.py — do not hand-edit.")
    lines.append("// Lab 9B recipe-domain KG fixture. Seed: %d." % SEED)
    lines.append("")

    # Constraint
    lines.append(
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
        "FOR (n:Entity) REQUIRE n.id IS UNIQUE;"
    )
    lines.append("")

    # Cuisines
    for name, parent in CUISINE_HIERARCHY:
        i = cid("Cuisine", name)
        lines.append(
            f"MERGE (n:Cuisine:Entity {{id: '{i}'}}) SET n.name = '{name}';"
        )
    lines.append("")

    cuisine_subclass = 0
    for name, parent in CUISINE_HIERARCHY:
        if parent is None:
            continue
        # Parent rename: if parent was renamed, the parent name on the
        # original side is "World"|"Asian"|... none of which are in the
        # rename map, so parent names are stable here.
        c = cid("Cuisine", name)
        p = cid("Cuisine", parent)
        lines.append(
            f"MATCH (c:Cuisine:Entity {{id: '{c}'}}), (p:Cuisine:Entity {{id: '{p}'}}) "
            f"MERGE (c)-[:SUBCLASS_OF]->(p);"
        )
        cuisine_subclass += 1
    lines.append("")

    # Ingredients
    for name, category, _parent in INGREDIENTS:
        i = cid("Ingredient", name)
        lines.append(
            f"MERGE (n:Ingredient:Entity {{id: '{i}'}}) "
            f"SET n.name = '{name}', n.category = '{category}';"
        )
    lines.append("")

    ingredient_subclass = 0
    for name, _category, parent in INGREDIENTS:
        if parent is None:
            continue
        c = cid("Ingredient", name)
        p = cid("Ingredient", parent)
        lines.append(
            f"MATCH (c:Ingredient:Entity {{id: '{c}'}}), (p:Ingredient:Entity {{id: '{p}'}}) "
            f"MERGE (c)-[:SUBCLASS_OF]->(p);"
        )
        ingredient_subclass += 1
    lines.append("")

    # Authors
    for name, country in AUTHORS:
        i = cid("Author", name)
        lines.append(
            f"MERGE (n:Author:Entity {{id: '{i}'}}) "
            f"SET n.name = '{name}', n.country = '{country}';"
        )
    lines.append("")

    # Techniques
    for name in TECHNIQUES:
        i = cid("Technique", name)
        lines.append(
            f"MERGE (n:Technique:Entity {{id: '{i}'}}) SET n.name = '{name}';"
        )
    lines.append("")

    # Recipes (120)
    cuisine_names = [n for (n, _p) in CUISINE_HIERARCHY if n != "World"]  # don't assign root
    ingredient_names = [n for (n, _c, _p) in INGREDIENTS]
    author_names = [n for (n, _c) in AUTHORS]

    uses_ingredient = 0
    of_cuisine = 0
    by_author = 0
    requires_technique = 0
    recipes_meta: list[dict] = []

    for r in range(120):
        cuisine = rng.choice(cuisine_names)
        ing_count = rng.choices([2, 3, 4], weights=[1, 3, 1])[0]
        ingredients_used = rng.sample(ingredient_names, ing_count)
        author = rng.choice(author_names)
        tech_count = rng.choices([1, 2], weights=[1, 1])[0]
        techniques_used = rng.sample(TECHNIQUES, tech_count)
        first_ing = ingredients_used[0]
        rname = f"{cuisine} {first_ing} recipe {r+1}"
        rdesc = (
            f"A {cuisine.lower()} dish featuring "
            f"{', '.join(ingredients_used)}."
        )
        pop = rng.randint(1, 100)
        prep = rng.randint(10, 120)
        rid = cid("Recipe", f"r{r+1}")
        lines.append(
            f"MERGE (n:Recipe:Entity {{id: '{rid}'}}) "
            f"SET n.name = \"{rname}\", n.description = \"{rdesc}\", "
            f"n.popularityScore = {pop}, n.prepMinutes = {prep};"
        )
        # Relationships
        cid_cuisine = cid("Cuisine", cuisine)
        lines.append(
            f"MATCH (r:Recipe:Entity {{id: '{rid}'}}), "
            f"(c:Cuisine:Entity {{id: '{cid_cuisine}'}}) "
            f"MERGE (r)-[:OF_CUISINE]->(c);"
        )
        of_cuisine += 1
        cid_author = cid("Author", author)
        lines.append(
            f"MATCH (r:Recipe:Entity {{id: '{rid}'}}), "
            f"(a:Author:Entity {{id: '{cid_author}'}}) "
            f"MERGE (r)-[:BY_AUTHOR]->(a);"
        )
        by_author += 1
        for ing in ingredients_used:
            cid_ing = cid("Ingredient", ing)
            lines.append(
                f"MATCH (r:Recipe:Entity {{id: '{rid}'}}), "
                f"(i:Ingredient:Entity {{id: '{cid_ing}'}}) "
                f"MERGE (r)-[:USES_INGREDIENT]->(i);"
            )
            uses_ingredient += 1
        for tech in techniques_used:
            cid_tech = cid("Technique", tech)
            lines.append(
                f"MATCH (r:Recipe:Entity {{id: '{rid}'}}), "
                f"(t:Technique:Entity {{id: '{cid_tech}'}}) "
                f"MERGE (r)-[:REQUIRES_TECHNIQUE]->(t);"
            )
            requires_technique += 1
        recipes_meta.append({
            "id": rid,
            "name": rname,
            "cuisine": cuisine,
            "ingredients": ingredients_used,
            "author": author,
            "techniques": techniques_used,
        })

    counts = {
        "nodes": {
            "Recipe": 120,
            "Cuisine": 16,
            "Ingredient": 40,
            "Author": 12,
            "Technique": 12,
            "total": 200,
        },
        "rels": {
            "USES_INGREDIENT": uses_ingredient,
            "OF_CUISINE": of_cuisine,
            "BY_AUTHOR": by_author,
            "REQUIRES_TECHNIQUE": requires_technique,
            "SUBCLASS_OF_cuisine": cuisine_subclass,
            "SUBCLASS_OF_ingredient": ingredient_subclass,
            "total": (
                uses_ingredient + of_cuisine + by_author
                + requires_technique + cuisine_subclass + ingredient_subclass
            ),
        },
        "recipes": recipes_meta,
    }
    return ("\n".join(lines) + "\n", counts)


# ---------------------------------------------------------------------------
# JSONL document generation
# ---------------------------------------------------------------------------

# Surface forms that participate in deliberate ambiguity / NIL seeding.
AMBIGUOUS_PAIRS = [
    # (surface, possible NER labels, possible KG resolutions)
    ("orange",  ["FOOD", "INGREDIENT"], [("ingredient:orange", "Ingredient")]),
    ("Orange",  ["FOOD", "GPE"],        [("cuisine:orange", "Cuisine")]),
    ("turkey",  ["INGREDIENT", "FOOD"], [("ingredient:turkey", "Ingredient")]),
    ("Turkish", ["FOOD", "GPE"],        [("cuisine:turkish", "Cuisine")]),
    ("basil",   ["INGREDIENT"],         [("ingredient:basil", "Ingredient")]),
    ("Basil Hawthorne", ["PERSON"],     [("author:basil-hawthorne", "Author")]),
    ("sage",    ["INGREDIENT"],         [("ingredient:sage", "Ingredient")]),
    ("Sage Mitchell", ["PERSON"],       [("author:sage-mitchell", "Author")]),
]

NIL_SURFACES = [
    ("kohlrabi", "INGREDIENT"),
    ("Andorran", "GPE"),
    ("dragonfruit", "INGREDIENT"),
    ("Bhutanese", "GPE"),
    ("yuzu", "INGREDIENT"),
]


def _gold_for_recipe_mention(name: str, label: str) -> tuple[str, str]:
    return cid(label, name), label


def gen_doc(rng: random.Random, recipes_meta: list[dict], doc_id: str,
            ambiguity_share: float, nil_share: float) -> dict:
    """Generate one short document with NER spans + gold annotations.

    Each doc has 4-7 spans drawn from a recipe's slot fillers, plus an
    optional ambiguous or NIL span seeded for disambiguation testing.
    """
    recipe = rng.choice(recipes_meta)
    # Choose 4-6 mentions
    base_mentions: list[tuple[str, str, str | None]] = []
    # 1 cuisine
    base_mentions.append((recipe["cuisine"], "GPE", ("Cuisine", recipe["cuisine"])))
    # 2-3 ingredients
    chosen_ings = rng.sample(
        recipe["ingredients"], min(3, len(recipe["ingredients"]))
    )
    for ing in chosen_ings:
        base_mentions.append((ing, "INGREDIENT", ("Ingredient", ing)))
    # 1 author
    base_mentions.append((recipe["author"], "PERSON", ("Author", recipe["author"])))
    # 1 technique with FOOD-ish NER label "TECHNIQUE"
    if recipe["techniques"]:
        t = rng.choice(recipe["techniques"])
        base_mentions.append((t, "TECHNIQUE", ("Technique", t)))

    # Optional ambiguous seed
    if rng.random() < ambiguity_share:
        amb = rng.choice(AMBIGUOUS_PAIRS)
        surface, labels, resolutions = amb
        ner_label = rng.choice(labels)
        node_id, type_label = resolutions[0]
        base_mentions.append((surface, ner_label, ("__abs", (node_id, type_label))))
    # Optional NIL seed
    if rng.random() < nil_share:
        s, l = rng.choice(NIL_SURFACES)
        base_mentions.append((s, l, None))

    # Build a sentence from these mentions
    pieces = []
    spans: list[list] = []
    gold: list[dict] = []
    offset = 0
    intros = [
        f"This {recipe['cuisine'].lower()} recipe by",
        f"A traditional {recipe['cuisine'].lower()} dish from",
        f"In this {recipe['cuisine'].lower()} kitchen,",
    ]
    intro = rng.choice(intros) + " "
    pieces.append(intro)
    offset += len(intro)

    for idx, (surface, ner_label, gold_spec) in enumerate(base_mentions):
        # Add a separator between mentions
        if idx > 0:
            sep = rng.choice([" and ", ", with ", ", featuring ", " using "])
            pieces.append(sep)
            offset += len(sep)
        start = offset
        pieces.append(surface)
        end = offset + len(surface)
        offset = end
        spans.append([start, end, surface, ner_label])
        if gold_spec is None:
            gold.append({
                "start": start, "end": end, "surface": surface,
                "gold_node_id": None, "gold_type_label": None,
            })
        elif gold_spec[0] == "__abs":
            node_id, type_label = gold_spec[1]
            gold.append({
                "start": start, "end": end, "surface": surface,
                "gold_node_id": node_id, "gold_type_label": type_label,
            })
        else:
            label, name = gold_spec
            gold.append({
                "start": start, "end": end, "surface": surface,
                "gold_node_id": cid(label, name), "gold_type_label": label,
            })

    pieces.append(".")
    return {
        "doc_id": doc_id,
        "text": "".join(pieces),
        "ner_spans": spans,
        "gold": gold,
    }


def gen_split(rng: random.Random, recipes_meta: list[dict],
              n_docs: int, prefix: str,
              ambiguity_share: float, nil_share: float) -> list[dict]:
    return [
        gen_doc(rng, recipes_meta, f"{prefix}-{i:04d}", ambiguity_share, nil_share)
        for i in range(n_docs)
    ]


def main() -> None:
    rng = random.Random(SEED)
    cypher, counts = build_cypher(rng)
    (HERE / "recipes_kg.cypher").write_text(cypher)

    # Generate splits with deterministic per-split seeds
    train_rng = random.Random(SEED + 1)
    dev_rng = random.Random(SEED + 2)
    test_rng = random.Random(SEED + 3)
    train = gen_split(train_rng, counts["recipes"], 80, "train", 0.18, 0.07)
    dev   = gen_split(dev_rng,   counts["recipes"], 20, "dev",   0.18, 0.07)
    test  = gen_split(test_rng,  counts["recipes"], 20, "test",  0.18, 0.07)

    for path, docs in [("train.jsonl", train),
                       ("dev.jsonl",  dev),
                       ("test.jsonl", test)]:
        with open(HERE / path, "w") as f:
            for d in docs:
                f.write(json.dumps(d) + "\n")

    print("Fixture counts:", json.dumps(counts["rels"], indent=2))
    print("Nodes:", json.dumps(counts["nodes"], indent=2))
    print(f"train: {len(train)} docs, "
          f"{sum(len(d['gold']) for d in train)} gold spans")
    print(f"dev:   {len(dev)} docs, "
          f"{sum(len(d['gold']) for d in dev)} gold spans")
    print(f"test:  {len(test)} docs, "
          f"{sum(len(d['gold']) for d in test)} gold spans")


if __name__ == "__main__":
    main()
