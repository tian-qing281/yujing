import json
import os
import re
from functools import lru_cache

import httpx
from dotenv import load_dotenv


DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def _get_llm_settings():
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("DEEPSEEK_API_BASE") or os.getenv("OPENAI_API_BASE") or DEFAULT_API_BASE
    model = os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL

    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable")

    return {
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
    }


@lru_cache(maxsize=1)
def get_llm():
    from langchain_openai import ChatOpenAI

    settings = _get_llm_settings()
    sync_client = httpx.Client(
        timeout=60.0,
        trust_env=False,
    )
    async_client = httpx.AsyncClient(
        timeout=60.0,
        trust_env=False,
    )
    return ChatOpenAI(
        model=settings["model"],
        openai_api_key=settings["api_key"],
        openai_api_base=settings["api_base"],
        temperature=0.35,
        max_tokens=800,
        max_retries=2,
        http_client=sync_client,
        http_async_client=async_client,
    )


def _clip_text(text: str, limit: int) -> str:
    if not text:
        return ""
    return text[:limit]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _material_context(markdown_text: str) -> str:
    if markdown_text and markdown_text.startswith("JSON_STREAM_LIST:"):
        try:
            stream = json.loads(markdown_text.replace("JSON_STREAM_LIST:", "", 1))
            lines = ["【舆情证据流】"]
            for index, post in enumerate(stream[:10]):
                author = post.get("author") or "匿名"
                time_text = post.get("time") or "未知时间"
                content = _strip_html(post.get("content_html", "")) or _strip_html(post.get("content", ""))
                source = post.get("source") or ""
                stats = post.get("stats") or post.get("metrics") or ""
                pieces = [f"{index + 1}. [{time_text}] {author}"]
                if source:
                    pieces.append(f"来源: {source}")
                if stats:
                    pieces.append(f"互动: {stats}")
                if content:
                    pieces.append(f"内容: {_clip_text(content, 160)}")
                lines.append(" | ".join(pieces))
            return "\n".join(lines)
        except Exception:
            return _clip_text(markdown_text, 1800)

    return _clip_text(_strip_html(markdown_text or "暂无正文"), 1800)


def _pretty_extra_info(extra_info: str) -> str:
    if not extra_info:
        return ""
    try:
        return json.dumps(json.loads(extra_info), ensure_ascii=False, indent=2)
    except Exception:
        return _clip_text(extra_info, 800)


async def analyze_article_content_stream(title: str, extra_info: str, markdown_text: str):
    from langchain_core.prompts import ChatPromptTemplate

    material_context = _material_context(markdown_text)
    context = (
        f"任务主题: {title}\n"
        f"背景信息:\n{_pretty_extra_info(extra_info)}\n\n"
        f"深度材料:\n{material_context}"
    )

    print("--- LLM FEED START ---")
    print(
        json.dumps(
            {
                "title": title,
                "extra_info": _pretty_extra_info(extra_info),
                "material_preview": _clip_text(material_context, 2400),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("--- LLM FEED END ---")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """你是一名资深舆情研判助手。请直接输出简洁、清晰、证据优先的分析正文，总字数控制在 350 字以内。

输出结构只允许两段：
1. 【核心事件】
2. 【深度研判】

要求：
- 先写材料里已经明确出现的事实，再做研判。
- 优先保留材料中出现的具体数字、时间、来源、对象和表述。
- 如果材料来自多条帖子，请综合主流观点、媒体通报和高互动评论，尽量交代事件背景、监管动作、争议焦点和公众反应。
- 如果材料里没有关键数字或时间，直接写“材料未提供”，不要脑补。
- 不要输出【趋势预判】。
- 不要编造背景，不要泛泛而谈，不要写空泛套话。
- 不要输出 JSON，不要多层列表，不要重复转述原文。""",
            ),
            ("user", "材料如下：\n\n{text}"),
        ]
    )

    try:
        chain = prompt | get_llm()
    except RuntimeError as exc:
        yield f"\n[配置错误] {exc}"
        return

    async for chunk in chain.astream({"text": context}):
        if chunk.content:
            yield chunk.content


def generate_morning_briefing():
    from langchain_core.prompts import ChatPromptTemplate

    from app.database import Article, SessionLocal

    db = SessionLocal()
    try:
        recent = db.query(Article).order_by(Article.pub_date.desc()).limit(30).all()
        if not recent:
            return "暂无新鲜事。"

        context = "\n".join([f"- {article.title}" for article in recent])
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "用一句话幽默总结过去 24 小时社会焦点情绪，不超过 60 字。"),
                ("user", "资讯：\n{context}"),
            ]
        )

        try:
            result = (prompt | get_llm()).invoke({"context": context})
        except RuntimeError as exc:
            return f"配置错误: {exc}"

        return result.content
    finally:
        db.close()


def chat_with_news(full_prompt: str) -> str:
    try:
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([("user", "{prompt}")])
        result = (prompt | get_llm()).invoke({"prompt": full_prompt})
        return result.content
    except RuntimeError as exc:
        return f"配置错误: {exc}"
    except Exception as exc:
        return f"研判引擎异常: {exc}"


async def chat_with_news_stream(system_prompt: str, history: list, current_query: str):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    messages = [SystemMessage(content=system_prompt)]

    for msg in history[-6:]:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content", "")))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg.get("content", "")))

    messages.append(HumanMessage(content=current_query))

    try:
        llm = get_llm()
    except RuntimeError as exc:
        yield f"\n[配置错误] {exc}"
        return

    try:
        async for chunk in llm.astream(messages):
            if chunk.content:
                yield chunk.content
    except Exception as exc:
        yield f"\n[指挥链路异常] {str(exc)}"


async def analyze_topic_macro_stream(topic_title: str, events: list):
    from langchain_core.prompts import ChatPromptTemplate

    event_context = "\n".join(
        [f"- 【事件{i+1}】: {e.get('title', '未知')}\n  概要: {e.get('summary', '暂无概要')}" for i, e in enumerate(events[:10])]
    )

    context = f"宏观主题: {topic_title}\n" f"关联子事件群:\n{event_context}"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """你是一名高级安全参谋。请对这一组互相关联的舆情事件进行“宏观态势总结”。
                
你的职责是：
1. 【态势总结】：用一段话概括目前该主题下所有事件的共同演进特征、涉及的主要平台火力和社会情绪。
2. 【核心风险】：分析这些事件交织在一起可能产生的次生影响、争议点或公众关注焦点。
3. 【关键节点】：提炼出该群组中最重要的2-3个关键事实。

要求：
- 语言风格：专业、精炼、工业化。
- 不要脑补细节，仅基于提供的子事件概要进行逻辑合成。
- 严禁空话套话，直接进入实质性研判。
- 不要输出 JSON 或多层嵌套。""",
            ),
            ("user", "输入材料：\n\n{text}"),
        ]
    )

    try:
        chain = prompt | get_llm()
    except RuntimeError as exc:
        yield f"\n[配置错误] {exc}"
        return

    async for chunk in chain.astream({"text": context}):
        if chunk.content:
            yield chunk.content


def analyze_article_content(title: str, extra_info: str, markdown_text: str) -> dict:
    return {"summary": "流式模式已启用", "sentiment": "Neutral"}
