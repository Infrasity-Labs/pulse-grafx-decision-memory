"""Step 1 proof: Pulse's embedding provider is the real model, not the stub.

Builds Pulse's own provider from its settings, loads the model and embeds three sentences.
Writes demo-state/step1/embedding.json. Exit code 1 if the provider is a stub or the model does not load.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATA_DIR", str(ROOT / ".work" / "pulse-home"))
os.environ.setdefault("PYTHONWARNINGS", "ignore")

from okto_pulse.community.adapters.embedding import build_community_embedding_provider  # noqa: E402
from okto_pulse.community.config import CommunitySettings  # noqa: E402


def main() -> int:
    s = CommunitySettings()
    p = build_community_embedding_provider(mode=s.kg_embedding_mode, model_name=s.kg_embedding_model, dim=s.kg_embedding_dim)
    meta0 = p.embedding_metadata()
    if meta0.get("is_stub", True):
        print("STUB embedding provider. Search results would be meaningless.")
        return 1
    p.preload()
    a, b, c = p.encode_batch(["How do we hash user passwords?", "Passwords are hashed with bcrypt before storage", "The blog post slug uses a slugify helper"])
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    out = {
        "configured_mode": s.kg_embedding_mode, "configured_model": s.kg_embedding_model, "configured_dim": s.kg_embedding_dim,
        "provider": type(p).__name__, "metadata_after_load": p.embedding_metadata(), "vector_length": len(a),
        "similarity_related_pair": round(dot(a, b), 3), "similarity_unrelated_pair": round(dot(a, c), 3),
    }
    state = Path(os.environ.get("DEMO_STATE", ROOT / "demo-state")) / "step1"
    state.mkdir(parents=True, exist_ok=True)
    (state / "embedding.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0 if out["similarity_related_pair"] > out["similarity_unrelated_pair"] + 0.2 else 1


if __name__ == "__main__":
    sys.exit(main())
