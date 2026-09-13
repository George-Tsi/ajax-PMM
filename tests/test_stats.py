from ajax_pmm.calibration.stats import bucket_index, calibration_table


def test_bucket_index_boundaries():
    assert bucket_index(0.0, 10) == 0
    assert bucket_index(0.99, 10) == 9
    assert bucket_index(1.0, 10) == 9  # must not spill into a nonexistent bucket 10


def test_bucket_index_mid_range():
    assert bucket_index(0.55, 10) == 5


def test_calibration_table_known_values():
    pairs = [(0.5, "yes"), (0.5, "no"), (0.5, "yes")]
    table = calibration_table(pairs, n_buckets=10)

    assert len(table) == 1
    row = table[0]
    assert row["bucket"] == 5
    assert row["n"] == 3
    assert row["mean_implied"] == 0.5
    assert row["realized_rate"] == 2 / 3


def test_calibration_table_skips_empty_buckets():
    pairs = [(0.05, "no"), (0.95, "yes")]
    table = calibration_table(pairs, n_buckets=10)

    buckets_present = {row["bucket"] for row in table}
    assert buckets_present == {0, 9}
