"""Retrieval evaluation: recall@k and MRR for each combination of signals.

Measures *retrieval only* (no LLM calls): is the file that answers the
question among the top-k chunks? Runs every question against several
retrieval configurations so we can see what each signal contributes.

Usage (from the repo root):
    python eval/run_eval.py                         # uses LLM_PROVIDER (openai needs a key)
    LLM_PROVIDER=fake python eval/run_eval.py       # offline, hashed embeddings
"""

from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.ingest.pipeline import build_index  # noqa: E402
from app.llm.provider import get_provider  # noqa: E402
from app.retrieval.retriever import search  # noqa: E402
from app.retrieval.store import RepoStore  # noqa: E402

K = 5
CONFIGS = {
    "vector only": frozenset({"vector"}),
    "keyword (BM25) only": frozenset({"keyword"}),
    "hybrid: vector + keyword": frozenset({"vector", "keyword"}),
    "hybrid + symbol match (default)": frozenset({"vector", "keyword", "symbol"}),
}


def main() -> None:
    spec = json.loads((ROOT / "eval" / "questions.json").read_text())
    settings = Settings(data_dir=Path(tempfile.mkdtemp(prefix="codewise-eval-")))
    provider = get_provider(settings)

    src = Path(tempfile.mkdtemp(prefix="codewise-eval-src-")) / "repo"
    subprocess.run(["git", "clone", "--depth", "1", "--branch", spec["ref"], spec["repo"], str(src)],
                   check=True, capture_output=True)

    index, sources = build_index("eval", "eval", src, settings)
    embeddings = provider.embed([c.embed_text for c in index.chunks])
    store = RepoStore(settings.data_dir)
    store.save(index, embeddings, sources)
    repo = store.load("eval")

    questions = spec["questions"]
    qvecs = provider.embed([q["q"] for q in questions])

    results: dict[str, list[int | None]] = {}
    for name, use in CONFIGS.items():
        ranks = []
        for q, qvec in zip(questions, qvecs):
            hits = search(repo, q["q"], qvec, candidate_k=30, use=use)
            files = [h.chunk.path for h in hits]
            ranks.append(files.index(q["file"]) + 1 if q["file"] in files else None)
        results[name] = ranks

    lines = [
        f"# Retrieval eval: {spec['repo']} @ {spec['ref']}",
        "",
        f"Embeddings: `{provider.embedder.name}` · {len(index.chunks)} chunks · {len(questions)} questions",
        "",
        f"| Configuration | Recall@{K} | MRR |",
        "|---|---|---|",
    ]
    for name, ranks in results.items():
        recall = sum(1 for r in ranks if r and r <= K) / len(ranks)
        mrr = sum(1 / r for r in ranks if r) / len(ranks)
        lines.append(f"| {name} | {recall:.2f} | {mrr:.2f} |")

    lines += ["", "Rank of the first chunk from the expected file (`-` = not in top 30):", "",
              "| Question | " + " | ".join(CONFIGS) + " |", "|---|" + "---|" * len(CONFIGS)]
    for i, q in enumerate(questions):
        cells = [str(results[n][i] or "-") for n in CONFIGS]
        lines.append(f"| {q['q']} | " + " | ".join(cells) + " |")

    report = "\n".join(lines) + "\n"
    out = ROOT / "eval" / f"results_{provider.embedder.name}.md"
    out.write_text(report)
    print(report)
    print(f"Saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
