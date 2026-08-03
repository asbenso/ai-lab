"""Scratch demo: embed two IAM doc chunks and compare cosine similarity."""

from __future__ import annotations

import math
from pathlib import Path

from langchain.embeddings import init_embeddings

CORPUS = Path("data/sample-corpus/aws-docs/iam-rotation.md")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main() -> None:
    chunks = CORPUS.read_text(encoding="utf-8").split("\n\n")[:2]
    embedder = init_embeddings("bedrock:amazon.titan-embed-text-v2:0")
    vecs = embedder.embed_documents(chunks)
    print(f"chunk 0: {chunks[0][:60]}...")
    print(f"chunk 1: {chunks[1][:60]}...")
    print(f"cosine similarity: {cosine_similarity(vecs[0], vecs[1]):.4f}")


if __name__ == "__main__":
    main()
