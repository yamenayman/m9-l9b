"""Run the linker on the dev split and print P/R/F1.

Convenience harness: not the autograder. Use it locally to tune the
disambiguator before submitting.

Usage (with Neo4j running and `data/recipes_kg.cypher` already loaded):

    python run_dev_eval.py
"""
import json
import os
from pathlib import Path

from neo4j import GraphDatabase

from linker import link, score, GoldSpan


URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "testtest")

HERE = Path(__file__).parent
DEV_PATH = HERE / "data" / "dev.jsonl"


def load_split(path: Path):
    docs = []
    for line in path.read_text().splitlines():
        if line.strip():
            docs.append(json.loads(line))
    return docs


def main() -> None:
    docs = load_split(DEV_PATH)
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        all_predictions = []
        all_gold = []
        for d in docs:
            ner_spans = [tuple(s) for s in d["ner_spans"]]
            preds = link(driver, d["doc_id"], d["text"], ner_spans)
            all_predictions.extend(preds)
            for g in d["gold"]:
                all_gold.append(GoldSpan(
                    doc_id=d["doc_id"],
                    start=g["start"],
                    end=g["end"],
                    surface=g["surface"],
                    gold_node_id=g["gold_node_id"],
                    gold_type_label=g["gold_type_label"],
                ))
        m = score(all_predictions, all_gold)
        print(f"precision: {m['precision']:.4f}")
        print(f"recall:    {m['recall']:.4f}")
        print(f"f1:        {m['f1']:.4f}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
