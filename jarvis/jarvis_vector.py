# -*- coding: utf-8 -*-
"""Jarvis 向量数据库 — 基于 ChromaDB 的语义记忆检索"""
import os
import json
from jarvis_logger import get_logger

log = get_logger("vector")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    log.warning("ChromaDB 未安装，向量检索不可用。安装方式: pip install chromadb")


class VectorMemory:
    """向量记忆存储 — 提供比关键词匹配更精准的语义检索"""

    def __init__(self, persist_dir=None):
        if persist_dir is None:
            persist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chroma")
        self.persist_dir = persist_dir
        self.client = None
        self.collection = None
        self.enabled = False

        if CHROMA_AVAILABLE:
            try:
                os.makedirs(persist_dir, exist_ok=True)
                self.client = chromadb.PersistentClient(
                    path=persist_dir,
                    settings=Settings(anonymized_telemetry=False),
                )
                self.collection = self.client.get_or_create_collection(
                    name="jarvis_memories",
                    metadata={"hnsw:space": "cosine"},
                )
                self.enabled = True
                count = self.collection.count()
                log.info(f"向量数据库已就绪 ({count} 条向量记忆)")
            except Exception as e:
                log.error(f"向量数据库初始化失败: {e}")
                self.enabled = False
        else:
            log.info("向量数据库未启用（ChromaDB 未安装）")

    def add(self, fact_id, content, metadata=None):
        """添加一条向量记忆"""
        if not self.enabled:
            return False
        try:
            meta = metadata or {}
            meta["content"] = content
            self.collection.add(
                documents=[content],
                ids=[str(fact_id)],
                metadatas=[meta],
            )
            return True
        except Exception as e:
            log.error(f"向量记忆添加失败: {e}")
            return False

    def search(self, query, n_results=5):
        """语义检索最相关的记忆"""
        if not self.enabled or self.collection.count() == 0:
            return []
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count()),
            )
            items = []
            if results["documents"] and results["documents"][0]:
                for doc, dist, meta in zip(
                    results["documents"][0],
                    results["distances"][0],
                    results["metadatas"][0],
                ):
                    items.append({
                        "content": doc,
                        "distance": dist,
                        "metadata": meta,
                    })
            return items
        except Exception as e:
            log.error(f"向量检索失败: {e}")
            return []

    def delete(self, fact_id):
        """删除一条向量记忆"""
        if not self.enabled:
            return False
        try:
            self.collection.delete(ids=[str(fact_id)])
            return True
        except Exception as e:
            log.error(f"向量记忆删除失败: {e}")
            return False

    def count(self):
        """返回当前向量记忆数量"""
        if not self.enabled:
            return 0
        return self.collection.count()

    def clear(self):
        """清空所有向量记忆"""
        if not self.enabled:
            return
        try:
            ids = self.collection.get()["ids"]
            if ids:
                self.collection.delete(ids=ids)
            log.info("向量记忆已清空")
        except Exception as e:
            log.error(f"向量记忆清空失败: {e}")


# 全局单例
_vector_memory = None


def get_vector_memory():
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemory()
    return _vector_memory
