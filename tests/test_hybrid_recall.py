from scripts.geo_eval.hybrid_recall import fuse_candidate_lists


def test_fuse_candidate_lists_merges_scores_and_preserves_best_brand_diversity():
    lists = {
        "bm25": [
            {"url": "https://a.com/1", "brand": "A", "score": 10},
            {"url": "https://a.com/2", "brand": "A", "score": 9},
        ],
        "entity": [
            {"url": "https://b.com/1", "brand": "B", "score": 8},
        ],
    }

    fused = fuse_candidate_lists(lists, top_n=3, max_per_brand=1)

    assert [row["brand"] for row in fused] == ["A", "B"]
    assert fused[0]["matched_channels"] == ["bm25"]
    assert fused[1]["matched_channels"] == ["entity"]
