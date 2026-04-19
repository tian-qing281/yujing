from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List

class ArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str
    item_id: str
    rank: int = 99
    title: str
    url: Optional[str]
    pub_date: datetime
    extra_info: Optional[str]
    ai_summary: Optional[str] = None
    ai_sentiment: Optional[str] = None
    content: Optional[str] = None
    fetch_time: Optional[datetime] = None
    search_match_reasons: List[str] = Field(default_factory=list)
    search_highlight_title: Optional[str] = None
    search_highlight_excerpt: Optional[str] = None

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[dict]] = []

class CompareRequest(BaseModel):
    a: str
    b: str
    topic: Optional[str] = None  # 主题过滤词（可选），例如"对比微博和知乎对伊朗事件的看法" → topic="伊朗事件"
    history: Optional[List[dict]] = []

class ChatResponse(BaseModel):
    answer: str

class MCPResponse(BaseModel):
    answer: str
    summoned_items: Optional[List[ArticleResponse]] = None


class EventResponse(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    article_count: int = 0
    platform_count: int = 0
    latest_article_time: Optional[datetime] = None
    representative_article_id: Optional[int] = None
    primary_source_id: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)
    confidence: str = "signal"
    confidence_label: str = "单条信号"
    match_reasons: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EventDetailResponse(EventResponse):
    related_articles: List[dict] = Field(default_factory=list)


class TopicResponse(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    event_count: int = 0
    article_count: int = 0
    platform_count: int = 0
    latest_event_time: Optional[datetime] = None
    representative_event_id: Optional[int] = None
    primary_source_id: Optional[str] = None
    confidence: str = "emerging"
    confidence_label: str = "成型中"
    match_reasons: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TopicDetailResponse(TopicResponse):
    related_events: List[EventResponse] = Field(default_factory=list)
