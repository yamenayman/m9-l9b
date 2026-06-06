"""Load the recipe KG fixture into Neo4j and assert acceptance counts.

Reads `data/recipes_kg.cypher` and streams its MERGE statements through
the Bolt driver. Then runs the §2.4 count assertions and the §2.6
duplicate-detect Cypher. Exits with a non-zero status on any failure
so CI fails fast.

Environment variables:
  NEO4J_URI       (default: bolt://localhost:7687)
  NEO4J_USER      (default: neo4j)
  NEO4J_PASSWORD  (default: testtest)
"""
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase


URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "testtest")

HERE = Path(__file__).parent
CYPHER_PATH = HERE / "data" / "recipes_kg.cypher"

# Acceptance targets — match the Phase 3 build contract §2.4.
EXPECTED_NODE_TOTAL = 200
EXPECTED_REL_TOTAL = 787  # see data/_build_fixture.py for the exact breakdown
TOLERANCE = 0.05  # ±5%


def _split_statements(text: str) -> list[str]:
    """Split a Cypher file on `;` boundaries, skipping comment-only lines."""
    statements: list[str] = []
    buf: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0]  # strip end-of-line comments
        if not line.strip():
            buf.append("\n")
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            # Drop trailing semicolon — driver accepts either way but be clean.
            if stmt.endswith(";"):
                stmt = stmt[:-1]
            if stmt.strip():
                statements.append(stmt)
            buf = []
    return statements


def main() -> int:
    if not CYPHER_PATH.exists():
        print(f"ERROR: fixture not found at {CYPHER_PATH}", file=sys.stderr)
        return 2

    statements = _split_statements(CYPHER_PATH.read_text())
    if not statements:
        print("ERROR: fixture file contained no statements", file=sys.stderr)
        return 2

    print(f"Loading {len(statements)} Cypher statements from {CYPHER_PATH}...")

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        with driver.session() as s:
            # Wipe any prior state — guarantees idempotent loads.
            s.run("MATCH (n) DETACH DELETE n").consume()
            for i, stmt in enumerate(statements):
                try:
                    s.run(stmt).consume()
                except Exception as e:
                    print(
                        f"ERROR: statement {i} failed: {stmt!r}\n  {e}",
                        file=sys.stderr,
                    )
                    return 1

            # §2.4 node + rel count acceptance
            node_count = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rel_count = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            print(f"Nodes loaded: {node_count} (target {EXPECTED_NODE_TOTAL})")
            print(f"Rels loaded:  {rel_count} (target {EXPECTED_REL_TOTAL})")

            n_min = int(EXPECTED_NODE_TOTAL * (1 - TOLERANCE))
            n_max = int(EXPECTED_NODE_TOTAL * (1 + TOLERANCE) + 1)
            r_min = int(EXPECTED_REL_TOTAL * (1 - TOLERANCE))
            r_max = int(EXPECTED_REL_TOTAL * (1 + TOLERANCE) + 1)
            if not (n_min <= node_count <= n_max):
                print(
                    f"ERROR: node count {node_count} outside ±{TOLERANCE*100:.0f}% "
                    f"of {EXPECTED_NODE_TOTAL}",
                    file=sys.stderr,
                )
                return 1
            if not (r_min <= rel_count <= r_max):
                print(
                    f"ERROR: rel count {rel_count} outside ±{TOLERANCE*100:.0f}% "
                    f"of {EXPECTED_REL_TOTAL}",
                    file=sys.stderr,
                )
                return 1

            # §2.6 duplicate-detect Cypher
            dup_rows = list(s.run(
                "MATCH (n:Entity) "
                "WITH n.id AS id, count(*) AS c "
                "WHERE c > 1 "
                "RETURN id, c"
            ))
            if dup_rows:
                print(
                    f"ERROR: {len(dup_rows)} duplicate :Entity.id values found: "
                    f"{dup_rows[:5]}",
                    file=sys.stderr,
                )
                return 1

            print("OK: fixture loaded, counts within tolerance, identity unique.")
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
