"""方面级情感分析（ABSA）服务。

由于公开中文 ABSA 预训练模型（PyABSA 等）均训练于电商/餐饮语料，
在新闻舆情场景下抽取实体差、情感判错率高，本项目改用 LLM-based ABSA：
一次 LLM 调用同时输出"方面 + 情感 + 证据句"。
"""

import json
import re
from typing import List, Dict, Any

from app.llm import chat_with_news


_PROMPT = """你是舆情方面级情感分析（ABSA）专家。请从下文新闻中抽取 3-5 个核心"方面"（aspect），
每个方面给出该方面在文中的情感（positive / neutral / negative）以及一句最能体现该情感的证据句。

要求：
1. 方面优先级：人物 > 机构 > 政策/事件 > 行业/赛道 > 概念。每个方面 2-8 个汉字。
2. 不要泛泛的"市场""情况"等空词；优先抽具体实体或议题。
3. 情感只能取 positive / neutral / negative 三选一。
4. 证据句必须摘自原文（≤40 字），不要改写。
5. 严格输出 JSON 数组，不要任何解释、不要 markdown 包裹、不要代码块。

输出格式：
[
  {{"aspect": "方面名", "sentiment": "positive|neutral|negative", "evidence": "原文证据句"}}
]

【新闻标题】
{title}

【新闻正文】
{content}
"""


_SENT_MAP = {"positive": "positive", "neutral": "neutral", "negative": "negative",
             "正面": "positive", "中性": "neutral", "负面": "negative"}


def _safe_parse_json(text: str) -> List[Dict[str, Any]]:
    """LLM 偶尔会带 markdown 围栏或附带说明，做容错抽取。"""
    if not text:
        return []
    # 去 markdown 围栏
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"```\s*$", "", text.strip())
    # 抽第一个 JSON 数组
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return data


def extract_aspects(title: str, content: str) -> List[Dict[str, Any]]:
    """对单篇文章做方面级情感分析。

    返回结构（最多 5 项）：
        [{"aspect": "外交部", "sentiment": "positive", "evidence": "中方代表展现了风度。"}, ...]

    任何异常或解析失败均返回空列表（前端会回退到旧三色环）。
    """
    if not (title or content):
        return []
    title = (title or "")[:120]
    content = (content or "")[:1800]
    prompt = _PROMPT.format(title=title, content=content)
    try:
        raw = chat_with_news(prompt)
    except Exception:
        return []
    parsed = _safe_parse_json(raw)
    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        aspect = str(item.get("aspect", "")).strip()
        sentiment = _SENT_MAP.get(str(item.get("sentiment", "")).strip().lower(), "")
        evidence = str(item.get("evidence", "")).strip()
        if not aspect or not sentiment:
            continue
        if aspect in seen:
            continue
        seen.add(aspect)
        cleaned.append({
            "aspect": aspect[:12],
            "sentiment": sentiment,
            "evidence": evidence[:60],
        })
        if len(cleaned) >= 5:
            break
    return cleaned
