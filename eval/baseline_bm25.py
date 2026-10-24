"""Offline keyword baseline over exported, team-scoped paper chunks."""

import json
from pathlib import Path
import re
import unicodedata

from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    # Deliberately simple keyword baseline: no translation or morphological model.
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


def title_key(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def evidence_hit(evidence: dict, sources: list[dict]) -> bool:
    expected_title = title_key(evidence["paper"])
    return any(
        isinstance(source, dict)
        and isinstance(source.get("title"), str)
        and title_key(source["title"]) == expected_title
        and type(source.get("page")) is int
        and source["page"] >= 1
        and any(abs(source["page"] - page) <= 1 for page in evidence["pages"])
        for source in sources
    )


def load_corpus(path: Path, team_id: int) -> list[dict]:
    """Read the existing text/metadata shape; never modify the data service."""
    documents = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            document = json.loads(line)
            metadata = document["metadata"]
            if not isinstance(document["text"], str) or not document["text"].strip():
                raise ValueError
            if not isinstance(metadata, dict) or type(metadata.get("team_id")) is not int:
                raise ValueError
            if not isinstance(metadata.get("source"), str) or not metadata["source"].strip():
                raise ValueError
            if type(metadata.get("page")) is not int or metadata["page"] < 1:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"Invalid corpus record at line {number}") from None
        if metadata["team_id"] == team_id:
            documents.append(document)
    if not documents:
        raise ValueError("No corpus records for the selected team")
    return documents


class BM25Baseline:
    def __init__(self, documents: list[dict]):
        self.documents = [document for document in documents if tokenize(document["text"])]
        if not self.documents:
            raise ValueError("Corpus has no searchable text")
        self.tokens = [tokenize(document["text"]) for document in self.documents]
        self.index = BM25Okapi(self.tokens)

    def search(self, question: str, k: int = 5) -> list[dict]:
        if k < 1:
            raise ValueError("top-k must be positive")
        query = tokenize(question)
        if not query:
            return []
        scores = self.index.get_scores(query)
        # A zero score can still be a matching term in a tiny corpus. Do not
        # equate score > 0 with relevance, or return completely unmatched text.
        candidates = [i for i, tokens in enumerate(self.tokens) if set(query).intersection(tokens)]
        ranked = sorted(candidates, key=lambda i: (-float(scores[i]), i))[:k]
        return [{
            "title": self.documents[i]["metadata"]["source"],
            "page": self.documents[i]["metadata"]["page"],
            "score": float(scores[i]),
        } for i in ranked]
