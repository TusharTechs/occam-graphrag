"""Chunking and hybrid (dense + lexical) retrieval for the RAG pipeline.

This is a deliberately *competent* RAG baseline.  A strawman would make the
three-way comparison meaningless, so it uses sentence-window chunking, a real
embedding model and reciprocal-rank fusion with BM25 - and the infobox is kept
at the head of every chunk, because that is where the answerable facts live.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    text: str

    @property
    def embed_text(self) -> str:
        # Title is prepended so a chunk retains its subject even when the body
        # is a bare table row.
        return f"{self.title}\n{self.text}"


def chunk_document(doc: dict, target_tokens: int = 320, overlap: int = 60) -> list[Chunk]:
    """Split one corpus row into overlapping word-window chunks.

    The infobox block is emitted as its own leading chunk: it is dense with the
    exact fields the benchmark asks about, and letting it be sliced mid-table
    is the main way a RAG baseline loses answerable facts.
    """
    text = doc.get("text", "")
    title, doc_id = doc["title"], doc["doc_id"]
    out: list[Chunk] = []

    head, body = text, ""
    m = re.search(r"\n\s*\n", text)
    if text.lstrip().startswith("[Infobox") and m:
        head, body = text[:m.start()], text[m.end():]
        out.append(Chunk(f"{doc_id}::box", doc_id, title, head.strip()))
    else:
        body = text

    words = body.split()
    step = max(1, target_tokens - overlap)
    for i in range(0, len(words), step):
        window = words[i:i + target_tokens]
        if len(window) < 20 and out:
            break
        out.append(Chunk(f"{doc_id}::{i}", doc_id, title, " ".join(window)))
    return out or [Chunk(f"{doc_id}::0", doc_id, title, text[:2000])]


class HybridIndex:
    """Dense + BM25 retrieval with reciprocal-rank fusion.

    The embedding matrix is cached on disk keyed by a hash of the chunk ids, so
    a benchmark re-run does not pay the embedding cost again.
    """

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._emb: np.ndarray | None = None
        self._bm25 = None
        self._model = None
        # The benchmark fans out over threads and torch's encoder is not
        # thread-safe; concurrent encode() calls abort the process rather
        # than raising, so every use of the model is serialised.
        self._model_lock = threading.Lock()
        # Query vectors are precomputed on the main thread; see
        # `precompute_queries`.
        self._qcache: dict[str, np.ndarray] = {}

    # -- construction ------------------------------------------------------
    @classmethod
    def build(cls, docs: list[dict], cache_dir: str | Path = "artifacts/index",
              verbose: bool = True) -> "HybridIndex":
        chunks: list[Chunk] = []
        for d in docs:
            chunks.extend(chunk_document(d))
        idx = cls(chunks)
        idx._load_or_embed(Path(cache_dir), verbose=verbose)
        idx._build_bm25()
        return idx

    def _signature(self) -> str:
        h = hashlib.sha256()
        h.update(str(len(self.chunks)).encode())
        for c in self.chunks[::97]:                 # sparse sample is enough
            h.update(c.chunk_id.encode())
        h.update(EMBED_MODEL.encode())
        return h.hexdigest()[:16]

    def _model_lazy(self):
        with self._model_lock:
            return self._model_unlocked()

    def _model_unlocked(self):
        if self._model is None:
            from occam.net import ensure_tls_trust
            ensure_tls_trust("huggingface.co")   # model weights are fetched over HTTPS
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBED_MODEL)
        return self._model

    def _load_or_embed(self, cache_dir: Path, verbose: bool) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"emb-{self._signature()}.npy"
        if path.exists():
            self._emb = np.load(path)
            if verbose:
                print(f"  vector index: loaded {self._emb.shape[0]} chunks from cache")
            return
        if verbose:
            print(f"  vector index: embedding {len(self.chunks)} chunks (one-off) ...")
        model = self._model_lazy()
        vecs = model.encode([c.embed_text for c in self.chunks],
                            batch_size=256, convert_to_numpy=True,
                            normalize_embeddings=True, show_progress_bar=verbose)
        self._emb = vecs.astype(np.float32)
        np.save(path, self._emb)

    def _build_bm25(self) -> None:
        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi([_tok(c.embed_text) for c in self.chunks])

    def precompute_queries(self, queries: list[str]) -> None:
        """Embed every query up front, on the calling thread.

        torch aborts the process rather than raising when its encoder is driven
        from several threads at once, and a lock around it only serialises the
        crash window without removing it. Embedding the whole question set
        before the benchmark fans out keeps torch on one thread entirely; the
        workers then touch nothing but numpy and BM25, which are safe.
        """
        todo = [q for q in dict.fromkeys(queries) if q not in self._qcache]
        if not todo:
            return
        vecs = self._model_unlocked().encode(todo, batch_size=64,
                                             convert_to_numpy=True,
                                             normalize_embeddings=True)
        for q, v in zip(todo, vecs):
            self._qcache[q] = v.astype(np.float32)

    # -- retrieval ---------------------------------------------------------
    def search(self, query: str, k: int = 10, alpha: float = 60.0) -> list[tuple[Chunk, float]]:
        """Reciprocal-rank fusion of dense and lexical rankings.

        RRF is used rather than score blending because BM25 and cosine scores
        are not on a comparable scale, and rank fusion is stable without
        per-query tuning.
        """
        qv = self._qcache.get(query)
        if qv is None:
            with self._model_lock:
                qv = self._model_unlocked().encode([query], convert_to_numpy=True,
                                                   normalize_embeddings=True)[0]
        dense = np.argsort(-(self._emb @ qv))[:k * 5]
        lex = np.argsort(-np.asarray(self._bm25.get_scores(_tok(query))))[:k * 5]

        fused: dict[int, float] = {}
        for rank, i in enumerate(dense):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (alpha + rank)
        for rank, i in enumerate(lex):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (alpha + rank)
        top = sorted(fused.items(), key=lambda p: -p[1])[:k]
        return [(self.chunks[i], s) for i, s in top]


_TOK_RE = re.compile(r"[a-z0-9]+")


def _tok(s: str) -> list[str]:
    return _TOK_RE.findall(s.lower())
