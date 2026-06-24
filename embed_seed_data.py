#!/usr/bin/env python3
"""
RAG seed script — embeds text fields with Voyage AI and writes vectors to Supabase.

Tables seeded (only rows with NULL embeddings are touched, so reruns are safe):

  linq_design_templates   → `description`    → `embedding`
  linq_industry_knowledge → `facts`           → `embedding`
  linq_prompt_examples    → `user_prompt`     → `embedding`
  LinqMemory              → `original_prompt` → `prompt_embedding`
                          → `output_summary`  → `output_embedding`

Usage:
    python rag/embed_seed_data.py

Required env vars:
    SUPABASE_URL   — https://<project>.supabase.co
    SUPABASE_KEY   — service-role key (needs write access)
    VOYAGE_API_KEY — Voyage AI key

Optional:
    VOYAGE_MODEL       — override model        (default voyage-3)
    VOYAGE_BATCH_SIZE  — texts per API call    (default 20; Voyage max is 128)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3")
_BATCH = int(os.getenv("VOYAGE_BATCH_SIZE", "20"))


@dataclass
class _EmbedTarget:
    """One embedding column to compute for a table."""
    source_field: str   # column whose text we embed
    embed_col: str      # vector column we write to


# Tables that produce a single embedding vector
_SINGLE_EMBED: dict[str, _EmbedTarget] = {
    "linq_design_templates":   _EmbedTarget("description", "embedding"),
    "linq_industry_knowledge": _EmbedTarget("facts",       "embedding"),
    "linq_prompt_examples":    _EmbedTarget("user_prompt", "embedding"),
}

# LinqMemory has two independent embedding columns
_LINQ_MEMORY_TARGETS = [
    _EmbedTarget("original_prompt", "prompt_embedding"),
    _EmbedTarget("output_summary",  "output_embedding"),
]


def _require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        log.error("Missing required env var: %s", name)
        sys.exit(1)
    return val


def _embed_batch(vo: Any, texts: list[str]) -> list[list[float]]:
    result = vo.embed(texts, model=_MODEL, input_type="document")
    return result.embeddings


def _seed_single(supabase: Any, vo: Any, table: str, target: _EmbedTarget, pk: str = "id") -> None:
    """Embed one column for a table; skip rows that already have the vector."""
    resp = (
        supabase.table(table)
        .select(f"{pk},{target.source_field}")
        .is_(target.embed_col, "null")
        .execute()
    )
    rows: list[dict[str, Any]] = resp.data or []
    if not rows:
        log.info("  %s.%s — nothing to embed", table, target.embed_col)
        return

    log.info("  %s.%s — %d row(s)", table, target.embed_col, len(rows))
    skipped = 0

    for i in range(0, len(rows), _BATCH):
        batch = rows[i : i + _BATCH]
        texts, valid = [], []
        for row in batch:
            text = (row.get(target.source_field) or "").strip()
            if not text:
                log.warning("  row %s has empty %s — skipping", row[pk], target.source_field)
                skipped += 1
                continue
            texts.append(text)
            valid.append(row)

        if not texts:
            continue

        log.info("  embedding %d–%d …", i + 1, i + len(texts))
        try:
            vectors = _embed_batch(vo, texts)
        except Exception as exc:
            log.error("  Voyage API error at batch %d: %s", i, exc)
            raise

        for row, vec in zip(valid, vectors):
            supabase.table(table).update({target.embed_col: vec}).eq(pk, row[pk]).execute()

        if i + _BATCH < len(rows):
            time.sleep(0.3)

    log.info("  done (skipped %d empty rows)", skipped)


def run() -> None:
    supabase_url = _require_env("SUPABASE_URL")
    supabase_key = _require_env("SUPABASE_KEY")
    _require_env("VOYAGE_API_KEY")

    try:
        import voyageai
    except ImportError:
        log.error("voyageai not installed — run: pip install voyageai")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        log.error("supabase not installed — run: pip install supabase")
        sys.exit(1)

    sb = create_client(supabase_url, supabase_key)
    vo = voyageai.Client()

    log.info("Model: %s  batch: %d", _MODEL, _BATCH)

    # Single-embedding tables
    for table, target in _SINGLE_EMBED.items():
        log.info("── %s ──", table)
        _seed_single(sb, vo, table, target)

    # LinqMemory — two passes (prompt_embedding, output_embedding)
    log.info("── LinqMemory ──")
    for target in _LINQ_MEMORY_TARGETS:
        _seed_single(sb, vo, "LinqMemory", target)

    log.info("Seeding complete.")


if __name__ == "__main__":
    run()
