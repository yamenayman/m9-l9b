"""Identity Discipline helpers.

In a property graph, identity is not free the way it is for RDF URIs.
Every KG node must carry a canonical id derived from (label, name) so that
two surface mentions of "orange" resolve to the same node iff they refer
to the same entity. The :Entity uniqueness constraint declared in
data/recipes_kg.cypher enforces this.

`canonical_id` is fully implemented — do not modify. `merge_entity` has
one TODO: produce the parameterized Cypher MERGE statement and bound
parameter dict for the (label, name) pair (gated by the Lab 9B
autograder under Gate 1b).
"""
import re


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def canonical_id(label: str, name: str) -> str:
    """Return the canonical KG id for a (label, name) pair.

    Convention: '<label-lower>:<name-slug>'. Examples:
      canonical_id("Ingredient", "Orange")  -> "ingredient:orange"
      canonical_id("Cuisine", "Sichuan")    -> "cuisine:sichuan"
      canonical_id("Author", "Maria Rossi") -> "author:maria-rossi"

    Ambiguous surface forms get DIFFERENT ids because the label differs:
      canonical_id("Ingredient", "orange") -> "ingredient:orange"
      canonical_id("Cuisine",    "Orange") -> "cuisine:orange"
    """
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return f"{label.strip().lower()}:{slug}"


def merge_entity(label: str, name: str, extra_props: dict | None = None) -> tuple[str, dict]:
    """Build a parameterized Cypher MERGE statement for one entity node.

    Returns (cypher_string, params_dict). The caller invokes
    session.run(cypher_string, **params_dict).

    Required behaviour:
      - The node carries TWO labels: the domain label AND :Entity.
      - The MERGE key is the canonical id from canonical_id(label, name).
      - `name` is always set on the node.
      - Any keys in extra_props are set on the node.

    Example expected return for merge_entity("Ingredient", "ginger", {"category": "spice"}):
      ("MERGE (n:Ingredient:Entity {id: $id}) SET n.name = $name, n.category = $category",
       {"id": "ingredient:ginger", "name": "ginger", "category": "spice"})

    NOTE: the property keys in the SET clause must be a literal Cypher
    identifier list — do NOT pass property names as parameters, only
    property VALUES. The id MUST come through a parameter ($id).
    """
    extra = extra_props or {}
    node_id = canonical_id(label, name)

    # Build SET clause: always set name, plus one clause per extra prop.
    set_clauses = ["n.name = $name"] + [f"n.{k} = ${k}" for k in extra]
    set_clause = ", ".join(set_clauses)

    cypher = (
        f"MERGE (n:{label}:Entity {{id: $id}}) "
        f"SET {set_clause}"
    )
    params: dict = {"id": node_id, "name": name, **extra}
    return cypher, params
