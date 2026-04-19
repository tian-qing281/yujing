"""
Agent 工具 · semantic_search_articles

**语义**检索文章（vs `search_articles` 的字面匹配）：
1. 先用 MeiliSearch 取 query 的 top-1 作为种子文章
2. 调 `get_semantic_neighbors(seed_id)` 拿 BGE 向量的 top-k 近邻
3. 输出种子 + 邻居列表，带 cosine / composite 分数

与纯 Meili 的差别举例：
- Query "伊朗冲突升级" 时，Meili 可能只命中含"伊朗冲突"的文章；
  语义检索能顺藤摸瓜找到"霍尔木兹海峡关闭"、"伊朗导弹试射"这类
  表述不同但主题相关的文章。

降级路径：
- 语义索引未就绪（runtime before build_semantic_index） → 返回 hint
  建议 LLM 改调 `search_articles`
- Meili 没命中 → 尝试 DB LIKE 拿第一个匹配作为 seed
- seed 在语义索引中不存在（过于新） → 返回 hint
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "semantic_search_articles"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20


def _resolve_seed_article_id(query: str, source_id: str) -> Optional[int]:
    """拿 query 最匹配的 article.id 作为语义检索种子。"""
    from app.database import Article, SessionLocal
    from app.services.search_engine import meili

    db = SessionLocal()
    try:
        # 先试 Meili
        if meili.enabled:
            try:
                hits = meili.search_articles(
                    query,
                    limit=1,
                    source_id=(source_id or ""),
                )
                if hits:
                    return int(hits[0])
            except Exception:
                pass
        # fallback: DB LIKE 最新
        q_obj = db.query(Article).filter(Article.title.like(f"%{query}%"))
        if source_id:
            q_obj = q_obj.filter(Article.source_id == source_id)
        row = q_obj.order_by(Article.pub_date.desc()).first()
        return int(row.id) if row else None
    finally:
        db.close()


def _handler(
    q: str = "",
    limit: int = DEFAULT_LIMIT,
    source_id: str = "",
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.services.semantic_index import (
        get_semantic_index_status,
        get_semantic_neighbors,
    )

    query = (q or "").strip()
    if not query:
        return {
            "query": "",
            "neighbors": [],
            "hint": "关键词 q 不能为空。",
        }

    try:
        lim = int(limit) if limit else DEFAULT_LIMIT
    except (TypeError, ValueError):
        lim = DEFAULT_LIMIT
    lim = max(1, min(lim, MAX_LIMIT))

    status = get_semantic_index_status()
    if not status.get("ready"):
        return {
            "query": query,
            "neighbors": [],
            "semantic_index_ready": False,
            "hint": (
                "语义索引尚未构建。请改调 search_articles 做字面检索，"
                "或提示用户在管理页面触发 rebuild_events_semantic。"
            ),
        }

    seed_id = _resolve_seed_article_id(query, source_id)
    if seed_id is None:
        return {
            "query": query,
            "neighbors": [],
            "semantic_index_ready": True,
            "hint": "未找到与 query 匹配的种子文章，无法做语义扩展。",
        }

    try:
        result = get_semantic_neighbors(seed_id, limit=lim)
    except KeyError:
        return {
            "query": query,
            "seed_article_id": seed_id,
            "neighbors": [],
            "semantic_index_ready": True,
            "hint": (
                f"种子文章 #{seed_id} 尚未进入语义索引（通常是新文章）。"
                "请换关键词或改用 search_articles。"
            ),
        }

    # 给每个 neighbor 补上 _id / _type / _title 统一元字段
    neighbors = []
    for row in result.get("neighbors", []):
        neighbors.append({
            "_id": row.get("article_id"),
            "_type": "article",
            "_title": row.get("title"),
            "source_id": row.get("source_id") or "",
            "pub_date": row.get("pub_date"),
            "cosine": round(float(row.get("cosine") or 0.0), 4),
            "composite": round(float(row.get("composite") or 0.0), 4),
            "above_threshold": bool(row.get("above_threshold")),
        })

    source = result.get("source", {})
    return {
        "query": query,
        "semantic_index_ready": True,
        "threshold": result.get("threshold"),
        "seed": {
            "_id": source.get("article_id"),
            "_type": "article",
            "_title": source.get("title"),
            "source_id": source.get("source_id") or "",
            "pub_date": source.get("pub_date"),
        },
        "total": len(neighbors),
        "neighbors": neighbors,
    }


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "基于 BGE 向量的**语义**检索：先用 Meili 取 query 的 top-1 做种子，"
        "再用 FAISS 找 top-k 语义近邻。能找到表述不同但主题相关的文章。"
        "用于跨表述扩展证据。语义索引未就绪时返回 hint。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "关键词或短语，作为种子匹配的查询",
            },
            "limit": {
                "type": "integer",
                "description": "返回近邻数，1 ≤ 值 ≤ 20，默认 10",
                "minimum": 1,
                "maximum": 20,
            },
            "source_id": {
                "type": "string",
                "description": "用于种子筛选的平台过滤；留空表示跨平台",
            },
        },
        "required": ["q"],
    },
    handler=_handler,
)

default_registry.register(SPEC)
