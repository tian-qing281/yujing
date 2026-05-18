import os
from datetime import UTC, datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
DB_DIR = os.path.join(RUNTIME_DIR, "db")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_project_path(path_value: str, fallback: str) -> str:
    if not path_value:
        return fallback
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(BASE_DIR, path_value)


os.makedirs(DB_DIR, exist_ok=True)
# 数据库文件默认名与项目对齐为 yujing.db；保留 DATABASE_PATH 环境变量覆盖入口，
# 便于老部署通过 .env 指回历史文件（例如 runtime/db/hongsou.db）。
# DEMO_MODE ON 时优先切到独立的演示库，避免污染主库；DATABASE_PATH 显式覆盖优先级最高。
from app.config import DEMO_MODE as _DEMO_MODE, DEMO_DB_FILENAME as _DEMO_DB_FILENAME  # noqa: E402

if os.getenv("DATABASE_PATH"):
    DATABASE_PATH = _resolve_project_path(os.getenv("DATABASE_PATH"), os.path.join(DB_DIR, "yujing.db"))
elif _DEMO_MODE:
    DATABASE_PATH = os.path.join(DB_DIR, _DEMO_DB_FILENAME)
else:
    DATABASE_PATH = os.path.join(DB_DIR, "yujing.db")
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
    pub_date = Column(DateTime, default=utcnow)
    fetch_time = Column(DateTime, default=utcnow)
    extra_info = Column(Text) # JSON string for views, likes, etc
    # 供后续 AI 使用的扩展字段
    ai_summary = Column(Text, nullable=True) 
    ai_sentiment = Column(String(20), nullable=True)
    content = Column(Text, nullable=True) # Jina 抓取的原始 markdown
    # P1 增量聚类：记录该文章已被聚类落库到 Event 的时间；NULL 表示尚未聚类
    clustered_at = Column(DateTime, nullable=True, index=True)

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)  # JSON string
    sentiment = Column(String(20), nullable=True, default="neutral")
    article_count = Column(Integer, default=0)
    platform_count = Column(Integer, default=0)
    heat_score = Column(Float, default=0.0, index=True)
    latest_article_time = Column(DateTime, default=utcnow, index=True)
    representative_article_id = Column(Integer, nullable=True, index=True)
    primary_source_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    # P1 增量聚类：簇均值向量（L2 归一）+ 已合并文章数；用于在线挂载新文章
    centroid = Column(LargeBinary, nullable=True)
    centroid_count = Column(Integer, default=0)


class EventArticle(Base):
    __tablename__ = "event_articles"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    article_id = Column(Integer, nullable=False, index=True)
    relation_score = Column(Float, default=0.0)
    importance_score = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


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
    latest_event_time = Column(DateTime, default=utcnow, index=True)
    representative_event_id = Column(Integer, nullable=True, index=True)
    primary_source_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class TopicEvent(Base):
    __tablename__ = "topic_events"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, nullable=False, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    relation_score = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


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
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ===== 升级 4：个性化订阅（Subscription / Blocklist / UserProfile）=====
class Subscription(Base):
    """用户订阅条目。kind=keyword/source/event。"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, default="local", index=True)
    kind = Column(String(20), nullable=False, index=True)  # keyword | source | event
    value = Column(String(200), nullable=False)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, default=utcnow)
    # S1.2：订阅词 BGE 向量持久化（float32 L2 归一，限 keyword/event 两种 kind）
    embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(80), nullable=True)


class Blocklist(Base):
    """屏蔽关键词（命中标题/摘要即过滤）。"""
    __tablename__ = "blocklist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, default="local", index=True)
    term = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=utcnow)


class UserProfile(Base):
    """用户行为画像。整体存为 JSON。

    data 结构：{
      "view_history": [{article_id, ts, dwell_ms, source_id, title, aspects:[]}, ...]  # 最近 200 条
      "source_weights": {source_id: count, ...}
      "tag_weights": {keyword: count, ...}
      "aspect_weights": {aspect: count, ...}
    }
    """
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, unique=True, index=True, default="local")
    data = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ===== 启动期轻量迁移 =====
# SQLAlchemy `create_all` 不会修改已存在表结构，对现网增量加列时需要手动 ALTER。
# 这里只针对 SQLite 做幂等的 ADD COLUMN（缺则加，存在则跳），覆盖 P1 增量聚类引入的
# 新字段。新增字段都允许 NULL，不影响旧数据。
def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def ensure_migrations() -> None:
    """启动期幂等迁移；新增列都设为 NULL 默认，旧数据零影响。"""
    with engine.begin() as conn:
        # P1 增量聚类
        _ensure_column(conn, "articles", "clustered_at", "DATETIME")
        _ensure_column(conn, "events", "centroid", "BLOB")
        _ensure_column(conn, "events", "centroid_count", "INTEGER DEFAULT 0")
        # S1.2 订阅词向量持久化
        _ensure_column(conn, "subscriptions", "embedding", "BLOB")
        _ensure_column(conn, "subscriptions", "embedding_model", "VARCHAR(80)")

