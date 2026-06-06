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
    # TODO:
    # 1. Open a session on `driver`. Run a parameterized Cypher MATCH that
    #    selects every (:Entity) node whose lowercased `name` equals the
    #    lowercased $surface parameter. Pass $surface via session.run's
    #    keyword arguments — do NOT embed `surface` in the query string.
    # 2. For each returned row, build a dict with keys id, name, labels.
    #    Drop the "Entity" label from labels so callers only see domain labels.
    # 3. Return the list (may be empty).
    raise NotImplementedError(
        "candidates() is not yet implemented — see the Reading's "
        "Candidate Generation worked example and the Lab guide."
    )
