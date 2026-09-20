"""One-off build of the chunk + embedding index used by the RAG pipeline."""
import json, time
from occam.store.vectors import HybridIndex

docs = [json.loads(l) for l in open("data/corpus.jsonl") if l.strip()]
t = time.time()
idx = HybridIndex.build(docs)
print(f"chunks={len(idx.chunks)} built in {time.time()-t:.0f}s")
hits = idx.search("How many nations competed in Judo at the 2016 Summer Olympics - Women's 57 kg?", k=3)
for c, s in hits:
    print(f"  {s:.4f}  {c.title[:60]}")
