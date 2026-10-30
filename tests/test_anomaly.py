"""
Automated unit tests for statistical and baseline anomaly detection methods.
"""

from services.anomaly_service import AnomalyService


def test_budget_variance_anomaly_logic():
    # Normal variance: 10% overrun with 20% threshold
    res_normal = AnomalyService.detect_budget_variance_anomaly(budgeted=1000.0, actual=1100.0, overrun_threshold_pct=20.0)
    assert res_normal["is_anomaly"] is False
    assert res_normal["method"] == "Budget Variance"

    # Overrun anomaly: 40% overrun with 20% threshold
    res_outlier = AnomalyService.detect_budget_variance_anomaly(budgeted=1000.0, actual=1400.0, overrun_threshold_pct=20.0)
    assert res_outlier["is_anomaly"] is True
    assert res_outlier["score"] == 40.0
    assert "surpassing" in res_outlier["explanation"]

    # Unbudgeted significant expense
    res_unbudgeted = AnomalyService.detect_budget_variance_anomaly(budgeted=0.0, actual=2500.0)
    assert res_unbudgeted["is_anomaly"] is True
    assert res_unbudgeted["method"] == "Unbudgeted Expense"


def test_zscore_outlier_detection():
    # Distribution with clear outlier (15000 is far from the mean of ~2000)
    amounts = [2000.0, 2100.0, 1950.0, 2050.0, 2000.0, 2200.0, 15000.0]
    z_res = AnomalyService.detect_zscore_anomalies(amounts, z_threshold=2.0)

    # 15000 should be flagged
    assert z_res[-1]["is_anomaly"] is True
    assert z_res[-1]["score"] > 2.0
    assert "statistical outlier" in z_res[-1]["explanation"]

    # First normal elements should NOT be anomalies
    assert z_res[0]["is_anomaly"] is False


def test_iqr_outlier_detection():
    amounts = [100.0, 110.0, 105.0, 95.0, 120.0, 100.0, 900.0]
    iqr_res = AnomalyService.detect_iqr_anomalies(amounts, multiplier=1.5)

    assert iqr_res[-1]["is_anomaly"] is True
    assert iqr_res[0]["is_anomaly"] is False
    assert "Tukey upper fence" in iqr_res[-1]["explanation"]
