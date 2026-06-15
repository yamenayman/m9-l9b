"""Candidate generation against the recipe KG.

Given a surface form (the literal text of an NER span), return all
:Entity nodes whose `name` matches case-insensitively. Candidates may
span multiple domain labels — the disambiguator resolves which one is
correct.
"""


def candidates(driver, surface: str) -> list[dict]:
    """Return all candidate (:Entity) nodes whose `name` matches `surface`
    case-insensitively.

    Each returned dict has keys:
      - "id": the canonical KG node id (e.g., "ingredient:orange")
      - "name": the node's `name` property
      - "labels": a list of strings, the node's labels EXCLUDING "Entity"
        (so "Ingredient", "Cuisine", etc.)

    MUST use parameterized Cypher (`$surface`), not f-string interpolation.
    f-string interpolation of a surface form into a Cypher query is the
    silent-failure mode shown in the Reading — apostrophes in surface
    forms crash the parse, and an attacker-controlled surface could
    inject destructive Cypher.

    Suggested Cypher shape (NOT a complete implementation — you fill in
    the WHERE clause and the RETURN projection):

        MATCH (n:Entity)
        WHERE toLower(n.name) = toLower($surface)
        RETURN n.id AS id, n.name AS name, labels(n) AS labels

    Then drop the literal "Entity" label from each row's `labels` list
    before returning.
    """
    query = (
        "MATCH (n:Entity) "
        "WHERE toLower(n.name) = toLower($surface) "
        "RETURN n.id AS id, n.name AS name, labels(n) AS labels"
    )
    with driver.session() as session:
        rows = list(session.run(query, surface=surface))
    result = []
    for row in rows:
        labels = [lbl for lbl in row["labels"] if lbl != "Entity"]
        result.append({"id": row["id"], "name": row["name"], "labels": labels})
    return result
