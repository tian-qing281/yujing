import unittest

import numpy as np

from app.services.semantic_index import (
    SEMANTIC_THRESHOLD_FALLBACK,
    _compute_adaptive_thresholds,
    _otsu_threshold,
    _preview_clusters,
    _resolve_nlist,
)


class SemanticIndexTestCase(unittest.TestCase):
    def test_resolve_nlist_caps_by_dataset_size(self):
        self.assertEqual(_resolve_nlist(1, 64), 1)
        self.assertEqual(_resolve_nlist(16, 64), 4)
        self.assertEqual(_resolve_nlist(100, 64), 10)

    def test_otsu_threshold_finds_gap_between_two_modes(self):
        # 两簇分布 [0.1-0.3] 和 [0.7-0.9]，Otsu 应切在中间空隙内
        values = np.array([0.10, 0.15, 0.22, 0.28, 0.30, 0.72, 0.78, 0.83, 0.88, 0.90])
        threshold = _otsu_threshold(values, lo=0.0, hi=1.0, step=0.01)
        self.assertGreater(threshold, 0.30)
        self.assertLess(threshold, 0.72)

    def test_otsu_threshold_returns_lo_when_values_are_uniform(self):
        # 所有值相等 → 任意切点类间方差都是 0 → 保持初始 best_t=lo
        values = np.full(20, 0.5)
        threshold = _otsu_threshold(values, lo=0.30, hi=0.80, step=0.01)
        self.assertAlmostEqual(threshold, 0.30, places=6)

    def test_compute_adaptive_thresholds_fallback_when_sparse(self):
        """< 50 条有效 cosine 时，直接用兜底值，且 otsu_L1 / L2 均为 None"""
        result = _compute_adaptive_thresholds([0.55, 0.61, 0.66, 0.7])
        self.assertEqual(result["p_filter"], SEMANTIC_THRESHOLD_FALLBACK)
        self.assertEqual(result["p_merge"], SEMANTIC_THRESHOLD_FALLBACK)
        self.assertIsNone(result["otsu_L1"])
        self.assertIsNone(result["otsu_L2"])

    def test_compute_adaptive_thresholds_layered_on_bimodal_data(self):
        """有效样本足够时，双层 Otsu 应返回 L1 ≤ L2，且都落在允许搜索域"""
        # 60 个样本：一半噪声 [0.3, 0.5]，一半强相似 [0.7, 0.85]
        rng = np.random.default_rng(42)
        noise = rng.uniform(0.30, 0.50, size=30)
        high = rng.uniform(0.70, 0.85, size=30)
        values = np.concatenate([noise, high]).tolist()

        result = _compute_adaptive_thresholds(values)
        self.assertIsNotNone(result["otsu_L1"])
        self.assertIsNotNone(result["otsu_L2"])
        # L1 搜索域 [0.30, 0.75)，L2 搜索域 [L1, 0.90)
        self.assertGreaterEqual(result["otsu_L1"], 0.30)
        self.assertLess(result["otsu_L1"], 0.75)
        self.assertGreaterEqual(result["otsu_L2"], result["otsu_L1"])
        self.assertLess(result["otsu_L2"], 0.90)
        # 语义约束：合并线不低于过滤线
        self.assertGreaterEqual(result["p_merge"], result["p_filter"])

    def test_preview_clusters_groups_pairs_above_threshold(self):
        clusters = _preview_clusters(
            [1, 2, 3, 4],
            {
                (1, 2): 0.81,
                (2, 3): 0.79,
                (3, 4): 0.41,
            },
            0.75,
        )
        self.assertEqual(clusters[0], [1, 2, 3])
        self.assertEqual(clusters[1], [4])


if __name__ == "__main__":
    unittest.main()
