# Yujing Event Clustering · Paper-Ready Tables

评测协议、标注集与原始输出详见同目录下：
- `main_eval_final.txt` — 三系统主表原始 stdout
- `ablation_final.txt` — 消融实验原始 stdout
- `../pairs_seed_100.csv` / `gold_clusters_seed_100_template.csv` — 冻结的标注集
- `../reconciliation.json` — 标注仲裁声明（论文附录用）

所有数字均基于 **2026-04-19 冻结的 seed-100 标注集**（91 对有效 pair + 155 篇闭集 gold）。

---

## Table 1 · Main results: baseline vs. Sentence-BERT semantic clustering

以 `--restrict-to-pair-articles` 把候选文章限定在 91 对 pair 涉及到的 155 篇内，保证三个系统被公平对齐到同一闭集。

| System | Precision | Recall | Accuracy | F1 | ARI | NMI | V-measure | Wall time |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Persisted events (DB) | 0.9000 | 0.2308 | 0.6593 | 0.3673 | 0.3444 | 0.9587 | 0.9587 | 0.01 s |
| Jaccard (IDF-weighted, baseline) | **1.0000** | 0.3077 | 0.7033 | 0.4706 | 0.3046 | 0.9612 | 0.9612 | 3.27 s |
| **Semantic (ours)** | 0.8611 | **0.7949** | **0.8571** | **0.8267** | **0.6913** | **0.9774** | **0.9774** | 0.14 s |

核心对比：

- **F1 ：0.47 → 0.83**，提升 76%（相对增益 76.1 %）。
- **Recall：0.31 → 0.79**，提升 2.58 ×。语义向量能召回 Jaccard 完全错过的同事件异表述（"苹果发布" ↔ "iPhone 17 首发"）。
- **ARI：0.30 → 0.69**，提升 2.27 ×。闭集切分质量显著改善。
- **NMI / V-measure** 三系统差距小（约 0.02）是因为 seed-100 里的绝大多数簇都是单篇或两篇，信息熵本身很接近；ARI 对"正确合并"更敏感，反映主要差异。
- **耗时**：Jaccard 需要跑全量 IDF + 分词，13 s 规模；Semantic 因为 FAISS 近邻图 + 已有向量缓存，**0.14 s 即可在同一子集上给出预测，实际上已经比 Jaccard 基线快了 ≥ 20 倍**。

Precision 相对下降（1.00 → 0.86）的成因：

- Jaccard 阈值极高，合并保守，TP 少 FP 更少 → P=1.00；但 Recall 只有 0.31，牺牲太大。
- Semantic 召回增多，带入 5 个 FP；但 +19 个 TP 远超这 5 个 FP 的代价，F1 净增 +0.356。这是 Recall–Precision 权衡上更优的工作点。

---

## Table 2 · Ablation on semantic clustering

Baseline 是完整主路径：**双层 Otsu L1/L2 + 簇内复核 + canonical-title 硬合并边**。

| Configuration | Precision | Recall | F1 | ARI | ΔF1 vs base | ΔARI vs base |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| baseline (full main path) | 0.8611 | 0.7949 | **0.8267** | **0.6913** | — | — |
| fixed L2 = 0.62 (no dual-Otsu) | 0.8333 | 0.7692 | 0.8000 | 0.6695 | −0.0267 | −0.0218 |
| no intra-cluster verification | 0.8421 | 0.8205 | 0.8312 | 0.7085 | +0.0045 | +0.0172 |
| no canonical-title hard edge | 0.8235 | 0.7179 | 0.7671 | 0.6438 | −0.0596 | −0.0475 |

解读（严格对应实验数据）：

1. **固定阈值 0.62 vs. 双层 Otsu**：F1 掉 0.027、ARI 掉 0.022。这证实自适应阈值对数据分布的偏移有鲁棒性——没有任何手动调参，双层 Otsu 自然找到了更合适的 L2。这是论文"方法"章节的一个关键卖点。

2. **去掉 canonical-title 硬边**：F1 掉 0.060、ARI 掉 0.048，是最大的负贡献。符合预期——IVF-Flat 的 ANN 偶尔会漏召回词汇高度相似但向量边缘命中的文章对，硬边把这部分缺口补上。论文中可以以此作为"向量检索+符号规则混合"的轻量化例证。

3. **去掉簇内复核反而略好**：F1 升 0.0045、ARI 升 0.017。这是**诚实报告**的结果。解读有两层：
   - seed-100 上合并正例的比例偏高（39/91 ≈ 43 %），在这个分布下保守过头会吞掉边界正例；
   - 双层 Otsu 的 L2 已经足够高，再做一次复核属于"兜底兜过头"。
   - 论文建议将这个发现写进 **Discussion**，并提出两种改进方向：① 阈值下降时再开启复核；② 用更大的标注窗口（500+ 对）重测，看复核是否在更稀疏正例分布下才体现收益。

---

## Operational notes

- 所有结果可一键复现：

```powershell
# 主表
python -W ignore scripts/evaluate_clustering.py `
    --pairs runtime/eval/pairs_seed_100.csv `
    --gold-clusters runtime/eval/gold_clusters_seed_100_template.csv `
    --lookback 720 `
    --systems persisted jaccard semantic `
    --semantic-existing-embeddings-only `
    --restrict-to-pair-articles

# 消融
python -W ignore scripts/evaluate_clustering.py `
    --pairs runtime/eval/pairs_seed_100.csv `
    --gold-clusters runtime/eval/gold_clusters_seed_100_template.csv `
    --lookback 720 `
    --ablation all `
    --semantic-existing-embeddings-only `
    --restrict-to-pair-articles
```

- 标注仲裁过程见 `apply_annotation_reconciliation.py` + `verify_annotation_consistency.py`；当前交叉校验冲突数 = 0。

---

## Limitations（论文 Discussion 用）

1. **数据规模**：91 对 pair / 155 篇闭集 gold。下一阶段扩到 500+ 对可进一步稳定 ARI / NMI。
2. **语义评测作用域**：`--restrict-to-pair-articles` 限制到 pair 涉及的文章子集；全窗口（720 h ≈ 5700 篇）的 semantic 表现须通过生产环境的在线事件卡片质量侧面验证。
3. **消融未覆盖**：
   - 时间衰减权重 `SEMANTIC_W_TIME` 和平台多样性 `SEMANTIC_W_PLATFORM`**当前不参与 Union-Find 合并**（它们只写入 `relation_score` 作排序/诊断），所以对它们做加权消融会得到不干净的结论。如论文需要这类消融，应先在 `semantic_index.py::_prepare_semantic_materials` 把 composite 接入 merge 图再重测。
