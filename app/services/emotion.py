import os
import re
import threading

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


# 只保留"静默噪声"相关的开关；不再把整个进程钉成离线模式。
# 原先的 TRANSFORMERS_OFFLINE=1 / HF_DATASETS_OFFLINE=1 会污染其他模块（如 embedding.py 的 bge 下载），
# 而每个 from_pretrained 已显式传 local_files_only=True，精确达成离线加载，全局污染多此一举。
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


class EmotionEngine:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._ready = False
                    cls._instance._load_failed = False
                    cls._instance._loading = False
                    cls._instance._model = None
                    cls._instance._tokenizer = None
                    cls._instance._torch = None
                    cls._instance.labels = [
                        "中性",
                        "关注",
                        "喜悦",
                        "愤怒",
                        "悲伤",
                        "质疑",
                        "惊讶",
                        "厌恶",
                    ]
        return cls._instance

    def _start_background_load(self):
        """在后台守护线程中加载模型，不阻塞主线程。"""
        if self._loading or self._ready or self._load_failed:
            return
        self._loading = True

        def _do_load():
            model_name = "Johnson8187/Chinese-Emotion"
            try:
                self._torch = torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                print(f"[情绪引擎] 后台加载离线 BERT 模型，设备: {device}")
                self._tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    model_name,
                    local_files_only=True,
                ).to(device)
                self._ready = True
                print("[情绪引擎] 离线 BERT 情绪模型已就绪。")
            except Exception as exc:
                self._load_failed = True
                print(f"[情绪引擎] 离线模型加载失败，规则兜底: {exc}")
            finally:
                self._loading = False

        t = threading.Thread(target=_do_load, name="emotion-load", daemon=True)
        t.start()

    def _fallback_analyze(self, text: str):
        lowered = re.sub(r"\s+", "", text.lower())
        rules = {
            "愤怒": [
                "震怒", "愤怒", "愤慨", "气炸", "离谱", "荒谬", "谴责", "怒", "性侵", "暴力", "欺诈",
                "霸凌", "抗议", "打砸", "骂", "坑害", "侵犯", "残忍", "恶意", "强拆", "滥用",
            ],
            "悲伤": [
                "悲伤", "难过", "痛心", "遗憾", "去世", "身亡", "遇难", "哭", "哀悼",
                "牺牲", "坠毁", "溺亡", "丧生", "悲剧", "不幸", "殉职", "追悼", "灾难", "伤亡",
            ],
            "喜悦": [
                "喜悦", "开心", "高兴", "振奋", "惊喜", "利好", "庆祝", "欢呼",
                "夺冠", "突破", "成功", "获奖", "上线", "首发", "新高", "暴涨", "大涨", "涨停",
                "好消息", "点赞", "祝贺", "恭喜", "火爆", "爆款",
            ],
            "质疑": [
                "质疑", "疑问", "真假", "是否", "为什么", "存疑", "好奇", "调查",
                "辟谣", "造假", "虚假", "可信", "究竟", "黑幕", "内幕", "争议", "翻车",
            ],
            "惊讶": [
                "惊讶", "震惊", "竟然", "居然", "没想到", "突发", "爆了",
                "暴跌", "崩了", "炸了", "刷屏", "霸屏", "全网", "刷爆", "罕见", "历史首次",
                "封锁", "制裁", "停火", "开火", "战争", "冲突",
            ],
            "厌恶": [
                "恶心", "厌恶", "反感", "恶劣", "无语", "太脏",
                "丑闻", "腐败", "贪污", "塌方", "毒", "假冒", "骗局",
            ],
            "关注": [
                "回应", "约谈", "通报", "监管", "热搜", "讨论",
                "声明", "表态", "重磅", "独家", "紧急", "警告",
            ],
        }

        scores = {label: 0.0 for label in self.labels}
        scores["中性"] = 0.08

        for label, keywords in rules.items():
            for keyword in keywords:
                if keyword in lowered:
                    scores[label] += 1.0

        total = sum(scores.values())
        if total <= 0:
            return [{"label": "中性", "value": 1.0}]

        normalized = [{"label": label, "value": value / total} for label, value in scores.items() if value > 0]
        normalized.sort(key=lambda item: item["value"], reverse=True)
        return normalized

    def analyze(self, text: str):
        if not text:
            return []

        self._start_background_load()
        if self._ready and self._model:
            torch = self._torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            try:
                inputs = self._tokenizer(
                    text[:512],
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                ).to(device)
                with torch.no_grad():
                    outputs = self._model(**inputs)
                    scores = torch.nn.functional.softmax(outputs.logits, dim=1)[0]

                results = []
                for index, label in enumerate(self.labels):
                    results.append({"label": label, "value": float(scores[index])})
                return sorted(results, key=lambda item: item["value"], reverse=True)
            except Exception:
                pass

        return self._fallback_analyze(text)

    def analyze_batch(self, texts: list[str], batch_size: int = 8) -> list[list[dict]]:
        """批量推理：将 texts 分批送入 BERT，减少 forward pass 次数。

        返回与 texts 等长的列表，每个元素格式同 analyze() 的返回值。
        空文本位置返回 []。
        """
        if not texts:
            return []

        self._start_background_load()
        use_model = self._ready and self._model

        results: list[list[dict]] = [None] * len(texts)

        # 收集非空文本及其原始索引
        valid_indices = []
        valid_texts = []
        for i, t in enumerate(texts):
            if t:
                valid_indices.append(i)
                valid_texts.append(t[:512])
            else:
                results[i] = []

        if not valid_texts:
            return results

        if use_model:
            torch = self._torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            for start in range(0, len(valid_texts), batch_size):
                chunk = valid_texts[start : start + batch_size]
                chunk_indices = valid_indices[start : start + batch_size]
                try:
                    inputs = self._tokenizer(
                        chunk,
                        return_tensors="pt",
                        truncation=True,
                        padding=True,
                        max_length=512,
                    ).to(device)
                    with torch.no_grad():
                        outputs = self._model(**inputs)
                        all_scores = torch.nn.functional.softmax(outputs.logits, dim=1)

                    for j, idx in enumerate(chunk_indices):
                        row = []
                        for k, label in enumerate(self.labels):
                            row.append({"label": label, "value": float(all_scores[j][k])})
                        results[idx] = sorted(row, key=lambda item: item["value"], reverse=True)
                except Exception:
                    # 这一批失败，逐条降级到规则
                    for idx, txt in zip(chunk_indices, chunk):
                        results[idx] = self._fallback_analyze(txt)
        else:
            for idx, txt in zip(valid_indices, valid_texts):
                results[idx] = self._fallback_analyze(txt)

        return results


emotion_engine = EmotionEngine()
