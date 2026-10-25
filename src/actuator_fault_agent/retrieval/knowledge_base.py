import math
import re
from collections import Counter
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

from actuator_fault_agent.domain.models import Evidence

TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:[-_][A-Za-z0-9]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    compact = text.lower()
    tokens = TOKEN_PATTERN.findall(compact)
    # Chinese character bigrams improve recall without an external tokenizer.
    chinese = "".join(
        token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"
    )
    tokens.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return tokens


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    title: str
    content: str
    source: str
    locator: str


class LocalKnowledgeBase:
    """Small explainable BM25-like retriever for the zero-infrastructure demo."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.chunks = self._load_chunks(directory)
        self._tokenized = [tokenize(chunk.title + " " + chunk.content) for chunk in self.chunks]
        self._document_frequency = Counter()
        for tokens in self._tokenized:
            self._document_frequency.update(set(tokens))
        self._average_length = (
            sum(len(tokens) for tokens in self._tokenized) / len(self._tokenized)
            if self._tokenized
            else 1.0
        )

    @staticmethod
    def _load_chunks(directory: Path) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        if not directory.exists():
            return chunks
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            sections = re.split(r"(?m)^##\s+", text)
            document_title = path.stem
            if sections and sections[0].lstrip().startswith("# "):
                first_lines = sections[0].splitlines()
                document_title = first_lines[0][2:].strip()
                sections[0] = "\n".join(first_lines[1:])
            for index, section in enumerate(sections, start=1):
                section = section.strip()
                if not section:
                    continue
                lines = section.splitlines()
                title = document_title if index == 1 else lines[0].strip()
                content = section if index == 1 else "\n".join(lines[1:]).strip()
                if not content:
                    continue
                digest = sha1(f"{path.name}:{index}:{title}".encode()).hexdigest()[:12]
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"kb-{digest}",
                        title=title,
                        content=content,
                        source=path.name,
                        locator=f"section-{index}",
                    )
                )
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[Evidence]:
        if not self.chunks:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        total_documents = len(self.chunks)
        scores: list[tuple[float, int]] = []
        k1, b = 1.5, 0.75
        for index, tokens in enumerate(self._tokenized):
            frequencies = Counter(tokens)
            length = max(1, len(tokens))
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if frequency == 0:
                    continue
                document_frequency = self._document_frequency[token]
                inverse_frequency = math.log(
                    1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = frequency + k1 * (1 - b + b * length / self._average_length)
                score += inverse_frequency * frequency * (k1 + 1) / denominator
            scores.append((score, index))
        best = sorted(scores, reverse=True)[:top_k]
        maximum = max((score for score, _ in best), default=0.0) or 1.0
        return [
            Evidence(
                evidence_id=self.chunks[index].chunk_id,
                title=self.chunks[index].title,
                content=self.chunks[index].content,
                source=self.chunks[index].source,
                locator=self.chunks[index].locator,
                score=min(1.0, score / maximum),
            )
            for score, index in best
            if score > 0
        ]
