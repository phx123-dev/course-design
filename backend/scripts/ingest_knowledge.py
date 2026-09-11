# -*- coding: utf-8 -*-
"""知识库语料批量入库：扫描 knowledge/*.md，按标题切分入库（幂等）
用法：py -3.13 scripts/ingest_knowledge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import KNOWLEDGE_DIR
from app.db import SessionLocal, init_db
from app.services.rag.store import add_document


def parse_md(path: Path) -> tuple:
    """读取 md：首个 # 行作标题，其余为正文"""
    lines = path.read_text(encoding="utf-8").split("\n")
    title = path.stem
    for ln in lines:
        if ln.startswith("# "):
            title = ln[2:].strip()
            break
    return title, "\n".join(lines)


def ingest_all() -> int:
    init_db()
    db = SessionLocal()
    n = 0
    try:
        for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
            title, text = parse_md(f)
            add_document(db, title, text, source=f.name)
            n += 1
            print(f"  ✓ {title} <- {f.name}")
    finally:
        db.close()
    return n


if __name__ == "__main__":
    count = ingest_all()
    print(f"共入库 {count} 篇语料")
