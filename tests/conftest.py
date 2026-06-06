"""Session-scoped Neo4j driver fixture for the Lab 9B autograder."""
import os
import sys

import pytest
from neo4j import GraphDatabase

# Tests live in tests/; the linker package lives at the repo root in the
# student's repo (and at starter/ in staging). Put the repo root on
# sys.path so `import linker` resolves. Per the Autograder Test Path Rule,
# we use `..` — NEVER `../starter/`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "testtest")


@pytest.fixture(scope="session")
def driver():
    """A session-scoped Bolt driver. Tests share one driver; they manage
    their own sessions to avoid cross-test transaction interference."""
    d = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        with d.session() as s:
            s.run("RETURN 1").consume()
        yield d
    finally:
        d.close()
