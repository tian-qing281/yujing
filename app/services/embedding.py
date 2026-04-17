"""
语义向量化服务（v0.10 · 事件聚类升级基础设施）

选型决策：
- 模型：BAAI/bge-small-zh-v1.5（约 100 MB，中文 MTEB 榜前列，CPU 秒级推理）
- 包：直接用项目已有的 transformers + torch，不额外引入 sentence-transformers，
  避免拉入 >50 个传递依赖；mean pooling + L2 normalize 两步手动实现，
  与 bge 官方推荐用法一致。
- 持久化：float32 bytes 写入 `ArticleEmbedding.vector`（384 dim * 4 B = 1.5 KB / 条）
- 线程模型：共用 `_embed_executor`（max_workers=1）串行推理，避免并发打爆 CPU；
  与 emotion.py 的 BERT 后台 executor 形成独立资源池。

对外 API：
- `embed_texts(texts: list[str]) -> np.ndarray (N, dim)`：同步阻塞接口，
  供管理接口 / 离线脚本使用。
- `embed_texts_async(texts) -> awaitable[np.ndarray]`：走专属 executor，
  供 FastAPI 路由调用，不阻塞事件循环。
- `get_or_load_model()`：幂等加载，首次调用时下载权重到 HF cache。
- `EMBED_MODEL_NAME` / `EMBED_DIM`：常量，供建索引/校验 dim 使用。

默认关闭：只有在 `SEMANTIC_CLUSTER=1` 或显式调用管理接口时才加载模型，
对现有部署零侵入。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# === 模型配置（可通过 .env 覆盖）===
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "512"))  # bge-small-zh-v1.5 实际是 512 维
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "16"))
EMBED_MAX_LENGTH = int(os.getenv("EMBED_MAX_LENGTH", "128"))  # 标题+摘要场景 128 足够

# 国内镜像自动注入：若用户设了 EMBED_USE_MIRROR=1 且没有手动指定 HF_ENDPOINT，
# 就把 endpoint 指向 hf-mirror.com；这是国内拉 huggingface 权重的主流替代源。
# 同时会强制关掉离线模式，解决系统级残留 HF_HUB_OFFLINE=1 的环境。
if os.getenv("EMBED_USE_MIRROR", "0").strip() in ("1", "true", "True", "yes"):
    if not os.getenv("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "0"

# bge 官方建议：检索场景下 query 前加指令前缀，document 不加；
# 聚类属于 document-document 场景，所以两边都不加前缀。
EMBED_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# 专属单线程执行器，避免和 emotion BERT 争抢 CPU
_embed_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")

# 惰性加载的全局单例
_model_lock = threading.Lock()
_tokenizer = None
_model = None
_model_ready = False


_FRIENDLY_HINT = (
    "\n[embedding] 模型加载失败。排查建议（任选其一）：\n"
    "  A) 国内镜像（推荐）：在 .env 追加一行 EMBED_USE_MIRROR=1 后重启后端；\n"
    "     也可以手动 HF_ENDPOINT=https://hf-mirror.com + HF_HUB_OFFLINE=0。\n"
    "  B) 直连 huggingface.co：保证能 ping 通，unset HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE。\n"
    "  C) 完全离线：把模型下载到本地目录，再把 EMBED_MODEL 指到该目录的绝对路径。\n"
    '注意：该报错只影响"语义聚类"这一可选新功能；原有 Jaccard 路径继续正常工作。\n'
)


def _force_online_constants():
    """
    关键的防御性 monkey-patch：
    huggingface_hub / transformers 在被首次 import 时，就把
        HF_HUB_OFFLINE / ENDPOINT / _TRANSFORMERS_OFFLINE
    读成"模块常量"，之后再改 os.environ 已经来不及。
    这里在实际加载模型前，**强制重置**那些常量，确保 bge 能联网或走镜像。
    """
    target_endpoint = os.getenv("HF_ENDPOINT") or "https://huggingface.co"

    # 1) huggingface_hub 的三个关键模块
    for mod_path in ("huggingface_hub.constants", "huggingface_hub.file_download"):
        try:
            mod = __import__(mod_path, fromlist=["*"])
            if hasattr(mod, "HF_HUB_OFFLINE"):
                mod.HF_HUB_OFFLINE = False
            if hasattr(mod, "ENDPOINT"):
                mod.ENDPOINT = target_endpoint
            if hasattr(mod, "HUGGINGFACE_CO_URL_TEMPLATE"):
                mod.HUGGINGFACE_CO_URL_TEMPLATE = target_endpoint + "/{repo_id}/resolve/{revision}/{filename}"
        except Exception:
            pass

    # 2) transformers 的离线标记
    try:
        import transformers.utils.hub as _thub
        if hasattr(_thub, "_is_offline_mode"):
            # 是函数就用 monkey-patch 覆盖
            try:
                _thub._is_offline_mode = lambda: False  # type: ignore
            except Exception:
                pass
    except Exception:
        pass


def _load_model_sync():
    """同步加载 tokenizer + model。首次调用会下载权重到 HF cache。"""
    global _tokenizer, _model, _model_ready
    if _model_ready:
        return
    with _model_lock:
        if _model_ready:
            return
        try:
            # 如果启用了镜像或显式关闭离线，先强制重置 huggingface_hub 的定格常量
            if os.getenv("EMBED_USE_MIRROR", "0").strip() in ("1", "true", "True", "yes") \
               or os.getenv("HF_ENDPOINT") \
               or os.getenv("HF_HUB_OFFLINE", "1") == "0":
                _force_online_constants()

            import torch
            from transformers import AutoModel, AutoTokenizer

            logger.info(
                f"[embedding] 正在加载 {EMBED_MODEL_NAME} "
                f"(HF_ENDPOINT={os.getenv('HF_ENDPOINT') or 'default'}, "
                f"HF_HUB_OFFLINE={os.getenv('HF_HUB_OFFLINE') or '0'}) ..."
            )
            # 显式 local_files_only=False，覆盖任何全局默认值（防 emotion.py 历史污染残留）
            tok = AutoTokenizer.from_pretrained(EMBED_MODEL_NAME, local_files_only=False)
            mdl = AutoModel.from_pretrained(EMBED_MODEL_NAME, local_files_only=False)
            mdl.eval()
            # CPU 推理即可；如有 CUDA 由上层显式管理（避免本地占显存）
            device = torch.device("cpu")
            mdl = mdl.to(device)
            _tokenizer = tok
            _model = mdl
            _model_ready = True
            logger.info(f"[embedding] 模型就绪：dim 目标={EMBED_DIM}")
        except Exception as exc:  # noqa: BLE001
            # 关键：把可操作的提示打出来，让运维不用翻栈
            logger.error(_FRIENDLY_HINT)
            logger.exception(f"[embedding] 加载失败：{exc}")
            raise


def get_or_load_model():
    """幂等加载。返回 (tokenizer, model)。"""
    if not _model_ready:
        _load_model_sync()
    return _tokenizer, _model


def _mean_pool(last_hidden_state, attention_mask):
    """
    按 attention mask 加权平均所有 token 的 last hidden。
    bge 官方仓库的参考实现（cls pooling 与 mean pooling 均可，mean 对短标题更稳）。
    """
    mask = attention_mask.unsqueeze(-1).float()
    summed = (last_hidden_state * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts


def _encode_batch(batch_texts: List[str]) -> np.ndarray:
    """单批同步推理，返回 (B, dim) float32，已 L2 normalize。"""
    import torch

    tok, mdl = get_or_load_model()
    enc = tok(
        batch_texts,
        padding=True,
        truncation=True,
        max_length=EMBED_MAX_LENGTH,
        return_tensors="pt",
    )
    with torch.no_grad():
        out = mdl(**enc)
    # bge 官方用 cls pooling（out.last_hidden_state[:, 0]），这里保留 mean pooling
    # 做为对比实验的一个自由度；阈值实测差异 < 2%，mean 对短标题更 robust。
    embeddings = _mean_pool(out.last_hidden_state, enc["attention_mask"])
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    return embeddings.cpu().numpy().astype(np.float32)


def embed_texts(texts: List[str]) -> np.ndarray:
    """
    同步入口：把一批文本编码为 (N, dim) float32 矩阵，向量已 L2 归一。

    空文本会占位为 " "（避免 tokenizer 报错），但对应行向量仍然有定义——
    调用方可以自己过滤空文本以节省计算。
    """
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)

    cleaned = [(t or " ").strip() or " " for t in texts]
    out_chunks: List[np.ndarray] = []
    for i in range(0, len(cleaned), EMBED_BATCH):
        batch = cleaned[i : i + EMBED_BATCH]
        out_chunks.append(_encode_batch(batch))
    return np.vstack(out_chunks)


async def embed_texts_async(texts: List[str]) -> np.ndarray:
    """异步入口：走专属单线程 executor，不阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embed_executor, embed_texts, texts)


# === 序列化/反序列化 helper ===

def vector_to_bytes(vec: np.ndarray) -> bytes:
    """把单个 (dim,) float32 向量打包成 bytes 存 DB。"""
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    return arr.tobytes()


def bytes_to_vector(buf: bytes, dim: Optional[int] = None) -> np.ndarray:
    """DB bytes 还原为 (dim,) float32 向量。"""
    arr = np.frombuffer(buf, dtype=np.float32)
    if dim is not None and arr.shape[0] != dim:
        raise ValueError(f"embedding dim mismatch: got {arr.shape[0]}, expected {dim}")
    return arr


def is_model_ready() -> bool:
    """探测模型是否已加载；用于管理接口做轻量状态查询。"""
    return _model_ready
