"""
Statistical and baseline anomaly detection service.
Implements Z-Score, Interquartile Range (IQR), and Budget Variance methods
with full mathematical explainability for each flagged outlier.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd


class AnomalyService:
    @staticmethod
    def detect_budget_variance_anomaly(
        budgeted: float,
        actual: float,
        overrun_threshold_pct: float = 20.0,
    ) -> Dict[str, Any]:
        """Check if an expense exceeds its allocated budget by a defined percentage."""
        if budgeted <= 0:
            # If no budget was set and expense is significant (> $500), flag as unbudgeted
            if actual > 500.0:
                return {
                    "is_anomaly": True,
                    "method": "Unbudgeted Expense",
                    "score": round(actual, 2),
                    "threshold": 500.0,
                    "explanation": f"Unbudgeted expense of ${actual:,.2f} recorded without prior budget allocation.",
                }
            return {"is_anomaly": False, "method": "Unbudgeted Expense", "score": 0.0, "threshold": 0.0, "explanation": "Expense within normal range."}

        variance = actual - budgeted
        variance_pct = (variance / budgeted) * 100.0

        if variance_pct > overrun_threshold_pct:
            return {
                "is_anomaly": True,
                "method": "Budget Variance",
                "score": round(variance_pct, 1),
                "threshold": overrun_threshold_pct,
                "explanation": (
                    f"Actual expense (${actual:,.2f}) exceeded budgeted amount (${budgeted:,.2f}) "
                    f"by {variance_pct:.1f}%, surpassing the allowed {overrun_threshold_pct}% threshold."
                ),
            }

        return {
            "is_anomaly": False,
            "method": "Budget Variance",
            "score": round(variance_pct, 1),
            "threshold": overrun_threshold_pct,
            "explanation": f"Variance of {variance_pct:.1f}% is within the allowed {overrun_threshold_pct}% threshold.",
        }

    @staticmethod
    def detect_zscore_anomalies(
        amounts: List[float],
        z_threshold: float = 2.5,
    ) -> List[Dict[str, Any]]:
        """
        Detect outliers using the statistical Z-score: Z = (x - mean) / std.
        Requires at least 4 historical samples to establish a baseline.
        """
        n = len(amounts)
        if n < 4:
            return [
                {
                    "is_anomaly": False,
                    "method": "Z-Score",
                    "score": 0.0,
                    "threshold": z_threshold,
                    "explanation": f"Insufficient historical baseline (only {n} data points available; minimum 4 required).",
                }
                for _ in amounts
            ]

        arr = np.array(amounts, dtype=float)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr))

        if std_val == 0.0:
            return [
                {
                    "is_anomaly": False,
                    "method": "Z-Score",
                    "score": 0.0,
                    "threshold": z_threshold,
                    "explanation": "Zero standard deviation in baseline; amounts are identical.",
                }
                for _ in amounts
            ]

        results = []
        for val in arr:
            z = (val - mean_val) / std_val
            is_anomaly = bool(z > z_threshold)
            results.append({
                "is_anomaly": is_anomaly,
                "method": "Z-Score",
                "score": round(float(z), 2),
                "threshold": z_threshold,
                "mean": round(mean_val, 2),
                "std": round(std_val, 2),
                "explanation": (
                    f"Expenditure ${val:,.2f} is {z:.2f} standard deviations above historical mean (${mean_val:,.2f}). "
                    f"{'Flagged as statistical outlier (> ' + str(z_threshold) + ' sigma).' if is_anomaly else 'Within normal distribution.'}"
                ),
            })
        return results

    @staticmethod
    def detect_iqr_anomalies(amounts: List[float], multiplier: float = 1.5) -> List[Dict[str, Any]]:
        """
        Detect outliers using Interquartile Range (Tukey's Fences):
        Outlier if x > Q3 + (multiplier * IQR).
        """
        n = len(amounts)
        if n < 4:
            return [
                {
                    "is_anomaly": False,
                    "method": "IQR",
                    "score": 0.0,
                    "threshold": 0.0,
                    "explanation": "Insufficient sample size for quartile analysis (minimum 4 samples needed).",
                }
                for _ in amounts
            ]

        arr = np.array(amounts, dtype=float)
        q25, q75 = np.percentile(arr, [25, 75])
        iqr = q75 - q25
        upper_bound = q75 + (multiplier * iqr)

        results = []
        for val in arr:
            is_anomaly = bool(val > upper_bound)
            results.append({
                "is_anomaly": is_anomaly,
                "method": "IQR",
                "score": round(float(val), 2),
                "threshold": round(float(upper_bound), 2),
                "q25": round(float(q25), 2),
                "q75": round(float(q75), 2),
                "iqr": round(float(iqr), 2),
                "explanation": (
                    f"Amount ${val:,.2f} exceeds Tukey upper fence ${upper_bound:,.2f} (Q75 + {multiplier}*IQR). "
                    f"{'Flagged as upper quartile outlier requiring operational audit.' if is_anomaly else 'Within normal quartile distribution.'}"
                ),
            })
        return results
