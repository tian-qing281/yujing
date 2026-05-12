# 舆镜 YuJing · 方面级情感分析（ABSA）算法文档

> 专题深度文档。上下文：[项目说明](./项目说明.md) · [情感分析文档](./情感分析文档.md)（粗粒度 8 类）· [核心原理文档](./核心原理文档.md) · [评测指标文档](./评测指标文档.md)

---

## 一、问题与定位

### 1.1 与"粗粒度 8 类情感"的关系

舆镜内有两层情感分析：

| 层级 | 模型 | 粒度 | 输出 | 用途 |
|:---|:---|:---|:---|:---|
| **粗粒度** | `Johnson8187/Chinese-Emotion`（BERT 8 类） | 整篇文本 → 1 个情绪 | `中性 / 关注 / 喜悦 / 愤怒 / 悲伤 / 质疑 / 惊讶 / 厌恶` 分布 | 情感极性分布柱状图、事件雷达 |
| **方面级（ABSA）** | DeepSeek LLM（few-shot prompt） | 整篇文本 → N 个 `(aspect, sentiment, evidence)` 三元组 | `[{aspect, sentiment∈{pos,neu,neg}, evidence≤40 字}]` | 文章深度分析的"舆情倾向分析"卡 |

**为什么不用现成 ABSA 模型**：公开中文 ABSA 模型（如 PyABSA、SemEval 系预训练）几乎全部训练于电商/餐饮评论语料，新闻舆情场景下：
- **方面抽取**：误把"市场""情况"等空词当作 aspect
- **情感判定**：对"中央政策""事件主体"等舆情语境无法迁移
- **证据回溯**：纯标签输出，无法附原文证据句

故改用 **LLM-based ABSA**：一次 LLM 调用同时输出三元组，prompt 内嵌强约束 + few-shot 范式。

### 1.2 算法位置

| 模块 | 文件 |
|:---|:---|
| 抽取实现 | `app/services/absa.py` → `extract_aspects(title, content)` |
| API 端点 | `app/api/routes.py` → `/api/articles/{id}/analyze` SSE 中以 `event: aspects` 事件下发 |
| 前端渲染 | `yujing-ui/src/components/AnalysisModal.vue` → `.absa-list` |
| 缓存目录 | `runtime/absa_cache/<sha1>.json` |

---

## 二、Prompt 工程

### 2.1 完整 Prompt 模板

```text
你是舆情方面级情感分析（ABSA）专家。请从下文新闻中抽取 5-8 个核心"方面"（aspect），
每个方面给出该方面在文中的情感（positive / neutral / negative）以及一句最能体现该情感的证据句。

要求：
1. 方面优先级：人物 > 机构 > 政策/事件 > 行业/赛道 > 概念。
   每个方面 2-8 个汉字，应尽量覆盖文中出现的核心实体与议题。
2. 不要泛泛的"市场""情况"等空词；优先抽具体实体或议题。
3. 情感只能取 positive / neutral / negative 三选一。
4. 证据句必须摘自原文（≤40 字），不要改写。
5. 严格输出 JSON 数组，不要任何解释、不要 markdown 包裹、不要代码块。

输出格式：
[
  {"aspect": "方面名", "sentiment": "positive|neutral|negative", "evidence": "原文证据句"}
]

【新闻标题】
{title}

【新闻正文】
{content}
```

### 2.2 关键设计点

| 设计点 | 目的 |
|:---|:---|
| **方面优先级显式排序** | 强制模型先抓"实体"而非"概念"，避免输出「未来 / 影响 / 趋势」等空词 |
| **限定 5-8 个** | 既保证覆盖度又防止"全文复读"（实测 GPT-4o 不限数量时会输出 15+ 噪声 aspect） |
| **三选一情感** | 与下游可视化色板（绿/灰/红）一一对应 |
| **证据句 ≤40 字** | 卡片单行显示不溢出；强制摘自原文 → 可溯源 |
| **JSON 数组裸输出** | 不允许 markdown 围栏；下游解析容错（见 §3.2）兜底 |

### 2.3 失败模式与对策

| 失败模式 | 对策 |
|:---|:---|
| LLM 偶尔包 markdown ```` ```json …``` ```` | `_safe_parse_json` 正则去围栏 |
| LLM 给出"中性"/"正面"/"负面" 等中文标签 | `_SENT_MAP` 双语映射 |
| LLM 输出文字解释 + JSON | 正则 `\[[\s\S]*\]` 抽第一个 JSON 数组 |
| LLM 完全不返回 / 超时 | API 层 `asyncio.wait_for(timeout=12s)` 超时；前端收 `aspects: [], timeout: true` 回收骨架屏 |
| LLM 重复方面（"美国"/"美方"） | Prompt 阶段不去重；前端按 aspect 字符串去重 |

---

## 三、实现细节

### 3.1 调用链

```
analyze_article SSE
  │
  ├─ (其他 metadata：词云/8 类情感/事件…)
  │
  ├─ 检查 runtime/absa_cache/{sha1(title+content)}.json
  │     └─ 命中 → 直接发送 event:aspects（< 5ms）
  │
  └─ 未命中：
        asyncio.to_thread(extract_aspects, title, content)
        包裹 asyncio.wait_for(timeout=12s)
            │
            ├─ 成功 → cache_save + event:aspects
            ├─ 抽空 → event:aspects (空数组)
            └─ 超时/异常 → event:aspects (空数组 + timeout 标志)
```

### 3.2 容错解析

```python
def _safe_parse_json(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"```\s*$", "", text.strip())
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []
```

后续再做：字段白名单（仅 `aspect/sentiment/evidence`）+ `_SENT_MAP` 标签归一化 + 每条 evidence 截断到 40 字。

### 3.3 文件缓存策略

- **Key**：`sha1(title + "\x1e" + content)` —— 标题或正文任一字符变化即缓存失效
- **Value**：JSON 数组原样落盘
- **目录**：`runtime/absa_cache/<key>.json`，可定期清理（无 TTL，按需手动）
- **优势**：同一篇文章反复点开"开始深度分析" 第二次起延时 < 5ms（vs LLM 5-10s）
- **风险**：LLM 提供商或 prompt 升级后旧缓存仍命中。**升级 prompt 时建议：**
  ```powershell
  Remove-Item runtime/absa_cache/* -Force
  ```

---

## 四、性能与质量

### 4.1 时延分布（实测）

| 路径 | P50 | P95 | 备注 |
|:---|---:|---:|:---|
| 缓存命中 | 3 ms | 8 ms | 文件 IO |
| LLM 抽取（首次） | 5.2 s | 9.1 s | DeepSeek-chat，正文 1-3 KB |
| 超时上限 | — | 12 s | API 层 `asyncio.wait_for` |

### 4.2 质量观察（人工抽 30 篇）

| 维度 | 通过率 | 说明 |
|:---|---:|:---|
| 方面合理性 | 28/30 | 2 例有"市场"等空词溢出 |
| 情感判定 | 27/30 | 3 例对"中性吐槽"误判负面 |
| 证据句可溯源 | 30/30 | 全部能在原文 Ctrl+F 找到 |
| ≤40 字 | 30/30 | Prompt 约束生效 |

### 4.3 与传统方法对比

| 方案 | 抽取 P/R | 情感准确 | 证据 | 综合 |
|:---|:---:|:---:|:---:|:---|
| PyABSA（电商预训）+ 规则后处理 | 0.32 / 0.41 | 0.58 | × | 不可用于新闻 |
| jieba 词频 Top-N + 关键词字典情感 | 0.55 / 0.68 | 0.62 | × | 无情感细粒度 |
| **本方案 LLM-ABSA** | **0.91 / 0.87** | **0.90** | ✓ | 工程可落地 |

> 备注：抽取 P/R 以人工标注 30 篇为参照集，未做公开数据集对比（新闻 ABSA 缺权威中文测评集）。

---

## 五、前端呈现

`AnalysisModal.vue` 中 `.absa-list` 卡片列表渲染规则：

| 字段 | UI |
|:---|:---|
| `aspect` | 大号 chip（按 sentiment 着色：绿/灰/红） |
| `sentiment` | chip 背景色 + 图标（thumb-up/equal/thumb-down） |
| `evidence` | 灰色小号文字，单行截断（hover tooltip 看全文） |

**容器策略**：`.absa-list` 设 `max-height: 300px; overflow-y: auto`，让右侧 ABSA 卡总外高对齐左侧情感极性分布图（约 416 px），不会反向把左侧拉伸。

---

## 六、未来工作（路线图 → A.8）

- **采样微调**：用 `runtime/absa_cache/` 已有数据做 SFT，蒸馏到 7B 量级 → 推理 < 1s
- **跨段聚合**：长正文按段抽取后做 aspect 归并（同义词合并：美国/美方/华盛顿 → 美国）
- **情感强度**：从三档扩展为五档（very_neg / neg / neu / pos / very_pos），驱动雷达图

详见 [升级路线图](../升级路线图.md) A 序列。
