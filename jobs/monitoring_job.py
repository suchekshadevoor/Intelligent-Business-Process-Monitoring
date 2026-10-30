"""
Monitoring and Daily Report Scheduled Job Callbacks.
"""

from database.connection import get_db
from services.monitoring_service import MonitoringService
from services.report_service import ReportService
from config.settings import logger


def run_scheduled_monitoring() -> dict:
    """Execute monitoring rules evaluation and return result summary."""
    logger.info("Executing scheduled monitoring job...")
    with get_db() as db:
        res = MonitoringService.evaluate_all_rules(db)
        logger.info(f"Scheduled monitoring complete: {res['new_alerts_created']} new, {res['existing_alerts_refreshed']} refreshed.")
        return res


def run_scheduled_daily_report() -> dict:
    """Generate daily business performance report and archive it."""
    logger.info("Executing scheduled daily performance report generation...")
    with get_db() as db:
        res = ReportService.generate_daily_report(db, user="Scheduler")
        logger.info(f"Scheduled daily report complete. ID: {res['id']}")
        return res
