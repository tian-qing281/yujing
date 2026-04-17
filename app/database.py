import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
DB_DIR = os.path.join(RUNTIME_DIR, "db")


def _resolve_project_path(path_value: str, fallback: str) -> str:
    if not path_value:
        return fallback
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(BASE_DIR, path_value)


os.makedirs(DB_DIR, exist_ok=True)
# 数据库文件默认名与项目对齐为 yujing.db；保留 DATABASE_PATH 环境变量覆盖入口，
# 便于老部署通过 .env 指回历史文件（例如 runtime/db/hongsou.db）。
DATABASE_PATH = _resolve_project_path(
    os.getenv("DATABASE_PATH"),
    os.path.join(DB_DIR, "yujing.db"),
)
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

from sqlalchemy import event as sa_event

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
    pool_recycle=600,
)

@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String(50), index=True) # e.g., 'bilibili_hot'
    item_id = Column(String(100), unique=True, index=True) # uniquely identify the post
    rank = Column(Integer, default=99) # 榜单原始排名
    title = Column(String(255), nullable=False)
    url = Column(String(500))
    pub_date = Column(DateTime, default=datetime.utcnow)
    fetch_time = Column(DateTime, default=datetime.utcnow)
    extra_info = Column(Text) # JSON string for views, likes, etc
    # 供后续 AI 使用的扩展字段
    ai_summary = Column(Text, nullable=True) 
    ai_sentiment = Column(String(20), nullable=True)
    content = Column(Text, nullable=True) # Jina 抓取的原始 markdown

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)  # JSON string
    sentiment = Column(String(20), nullable=True, default="neutral")
    article_count = Column(Integer, default=0)
    platform_count = Column(Integer, default=0)
    latest_article_time = Column(DateTime, default=datetime.utcnow, index=True)
    representative_article_id = Column(Integer, nullable=True, index=True)
    primary_source_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventArticle(Base):
    __tablename__ = "event_articles"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    article_id = Column(Integer, nullable=False, index=True)
    relation_score = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)  # JSON string
    sentiment = Column(String(20), nullable=True, default="neutral")
    event_count = Column(Integer, default=0)
    article_count = Column(Integer, default=0)
    platform_count = Column(Integer, default=0)
    latest_event_time = Column(DateTime, default=datetime.utcnow, index=True)
    representative_event_id = Column(Integer, nullable=True, index=True)
    primary_source_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TopicEvent(Base):
    __tablename__ = "topic_events"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, nullable=False, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    relation_score = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class VirtualFTS(Base):
    # FTS5 Virtual Table mapping - we'll create this via raw SQL
    __tablename__ = "articles_fts"
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    # This is a dummy model just to let SQLAlchemy know about it if needed


class ArticleEmbedding(Base):
    """
    语义向量存储（v0.10 新增，用于事件聚类升级为 Sentence-BERT）。

    设计要点：
    - 独立出新表而不是膨胀 Article，避免主表迁移风险；
    - vector 列存 float32 的 numpy bytes（dim * 4 bytes），读取时 np.frombuffer 复原；
    - 多模型共存：同一 article_id + 不同 model_name 可以并存（便于做对照实验）；
    - 以 (article_id, model_name) 为业务主键，通过 Index 保证唯一性。
    """
    __tablename__ = "article_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, nullable=False, index=True)
    model_name = Column(String(80), nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    vector = Column(LargeBinary, nullable=False)  # float32 bytes, len == dim * 4
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
