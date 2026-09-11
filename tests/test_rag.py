# -*- coding: utf-8 -*-
"""RAG 知识库测试：切分 / 向量化 / 入库 / 混合检索命中质量"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import KnowledgeChunk, KnowledgeDoc, SessionLocal, init_db
from app.services.rag import splitter, store, vectorizer
from app.services.rag.retriever import search


class TestRAG(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        try:
            store.add_document(db, "测试文档-内圈故障处置", """
# 测试文档-内圈故障处置

## 特征

内圈故障特征频率 BPFI 约为 158Hz，频谱出现转频边带，峭度升高。

## 处置

计划停机更换轴承，检查轴颈配合。备件为同型号深沟球轴承与润滑脂。
""", source="单元测试")
            store.add_document(db, "测试文档-外圈故障处置", """
# 测试文档-外圈故障处置

## 特征

外圈故障特征频率 BPFO 约为 104Hz，频谱无显著边带，等幅冲击。

## 处置

检查轴承座孔配合，更换轴承并复测对中。
""", source="单元测试")
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        """清理测试文档，避免污染正式知识库"""
        db = SessionLocal()
        try:
            for doc in db.query(KnowledgeDoc).filter(KnowledgeDoc.source == "单元测试").all():
                db.query(KnowledgeChunk).filter_by(doc_id=doc.id).delete()
                db.delete(doc)
            db.commit()
        finally:
            db.close()

    def test_splitter_chunk_bounds(self):
        """切分：块大小在合理范围、字符定位与原文一致"""
        text = "# 标题\n\n" + "段落一。" * 30 + "\n\n## 小节\n\n" + "段落二。" * 20
        chunks = splitter.split_markdown(text)
        self.assertGreaterEqual(len(chunks), 2)
        for c in chunks:
            self.assertGreaterEqual(len(c["text"]), 30)
            self.assertLessEqual(len(c["text"]), 440)
            self.assertEqual(text[c["char_start"]:c["char_end"]], c["text"])

    def test_vectorizer_normalized(self):
        """向量化：L2 归一化（模长为 1）、确定性"""
        v1 = vectorizer.encode("滚动轴承内圈故障振动特征")
        v2 = vectorizer.encode("滚动轴承内圈故障振动特征")
        np.testing.assert_array_equal(v1, v2)
        self.assertAlmostEqual(float(np.linalg.norm(v1)), 1.0, places=4)

    def test_ingest_and_search_relevance(self):
        """入库后可检索：'内圈故障' 应命中内圈文档而非外圈文档"""
        db = SessionLocal()
        try:
            index = store.load_index(db)
            self.assertGreaterEqual(len(index["metas"]), 2)
            results = search(index, "内圈故障特征频率和处置方法", top_k=3)
            self.assertGreater(len(results), 0)
            # 第一名应为内圈相关文档
            self.assertIn("内圈", results[0]["doc_title"])
            # 引用编号按序生成
            self.assertEqual(results[0]["ref"], "[1]")
            self.assertGreater(results[0]["score"], 0)
            # 短查询"外圈故障"也应命中外圈文档
            results2 = search(index, "外圈故障", top_k=3)
            self.assertIn("外圈", results2[0]["doc_title"])
        finally:
            db.close()

    def test_stats(self):
        db = SessionLocal()
        try:
            s = store.stats(db)
            self.assertGreaterEqual(s["doc_count"], 2)
            self.assertGreaterEqual(s["chunk_count"], s["doc_count"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
