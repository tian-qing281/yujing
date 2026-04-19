import unittest

from app.services.semantic_index import _preview_clusters, _resolve_adaptive_threshold, _resolve_nlist


class SemanticIndexTestCase(unittest.TestCase):
    def test_resolve_nlist_caps_by_dataset_size(self):
        self.assertEqual(_resolve_nlist(1, 64), 1)
        self.assertEqual(_resolve_nlist(16, 64), 4)
        self.assertEqual(_resolve_nlist(100, 64), 10)

    def test_adaptive_threshold_uses_p95_when_scores_enough(self):
        threshold, p95 = _resolve_adaptive_threshold([0.40, 0.45, 0.51, 0.58, 0.60, 0.62, 0.70, 0.83, 0.91])
        self.assertIsNotNone(p95)
        self.assertGreaterEqual(threshold, 0.54)
        self.assertLessEqual(threshold, 0.78)
        self.assertGreaterEqual(p95, 0.83)

    def test_adaptive_threshold_falls_back_when_scores_sparse(self):
        threshold, p95 = _resolve_adaptive_threshold([0.55, 0.61, 0.66])
        self.assertEqual(threshold, 0.62)
        self.assertIsNone(p95)

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
