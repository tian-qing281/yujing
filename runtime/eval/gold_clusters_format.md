# Gold Cluster 标注格式

用途：
- `pair` 标注只适合算事件合并的 Precision / Recall / F1。
- `ARI / NMI / V-measure` 需要一份闭集 `gold cluster` 标注，也就是：
  在一个固定文章集合内，每篇文章都要被分配到一个人工定义的 `cluster_id`。

最小必需字段：
- `article_id`
- `cluster_id`

可选字段：
- `gold_cluster_title`
- `note`
- 任何辅助人工标注的字段，例如 `title`、`source_id`、`pub_date`

推荐工作流：
1. 先导出模板：

```powershell
python scripts/evaluate_clustering.py `
  --pairs runtime/eval/pairs_seed_100.csv `
  --lookback 720 `
  --semantic-existing-embeddings-only `
  --export-gold-template runtime/eval/gold_clusters_seed_100_template.csv
```

2. 在导出的模板里人工填写 `gold_cluster_id`。

3. 跑评测：

```powershell
python scripts/evaluate_clustering.py `
  --pairs runtime/eval/pairs_seed_100.csv `
  --gold-clusters runtime/eval/gold_clusters_seed_100_template.csv `
  --lookback 720 `
  --systems persisted jaccard semantic `
  --semantic-existing-embeddings-only `
  --restrict-to-pair-articles
```

说明：
- `cluster_id` 只要求在当前闭集里唯一且一致，例如 `G001`、`G002`。
- 同一事件的文章必须写同一个 `cluster_id`。
- 明显不是同一事件的文章必须分到不同 `cluster_id`。
- 单篇独立事件也要占一个独立 `cluster_id`。
- 当前评测脚本会自动忽略 `cluster_id` 为空的行。

现成文件：
- 模板：[runtime/eval/gold_clusters_seed_100_template.csv](runtime/eval/gold_clusters_seed_100_template.csv)
- 示例：[runtime/eval/gold_clusters_example.csv](runtime/eval/gold_clusters_example.csv)
