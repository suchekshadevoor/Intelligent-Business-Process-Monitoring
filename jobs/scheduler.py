"""
Background Scheduler Singleton Service.
Manages recurring monitoring and daily reporting jobs with protection against
duplicate scheduler instances during Streamlit application reruns.
"""

import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings, logger
from jobs.monitoring_job import run_scheduled_monitoring, run_scheduled_daily_report


class MonitoringScheduler:
    _instance: Optional["MonitoringScheduler"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MonitoringScheduler, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.scheduler = BackgroundScheduler(daemon=True)
        self.interval_minutes = settings.DEFAULT_MONITORING_INTERVAL_MINUTES
        self.is_running = False
        self.last_run_time: Optional[datetime] = None
        self.last_run_status: Optional[str] = None
        self.last_run_summary: Optional[dict] = None
        self.job_history: List[Dict[str, Any]] = []
        self._initialized = True

    def start(self, interval_minutes: Optional[int] = None) -> Dict[str, Any]:
        """Start the background scheduler if not already running."""
        with self._lock:
            if self.is_running and self.scheduler.running:
                return {"status": "already_running", "message": "Scheduler is already active."}

            if interval_minutes:
                self.interval_minutes = max(interval_minutes, 1)

            # Register recurring monitoring job
            if not self.scheduler.get_job("job_monitoring_rules"):
                self.scheduler.add_job(
                    func=self._wrapper_monitoring,
                    trigger=IntervalTrigger(minutes=self.interval_minutes),
                    id="job_monitoring_rules",
                    name="Evaluate Business Monitoring Rules",
                    replace_existing=True,
                )

            # Register daily report job (runs daily at 23:59 UTC)
            if not self.scheduler.get_job("job_daily_report"):
                self.scheduler.add_job(
                    func=self._wrapper_daily_report,
                    trigger=CronTrigger(hour=23, minute=59),
                    id="job_daily_report",
                    name="Daily Executive Report Generator",
                    replace_existing=True,
                )

            if not self.scheduler.running:
                self.scheduler.start()

            self.is_running = True
            logger.info(f"Background scheduler started (interval: {self.interval_minutes}m).")
            return {
                "status": "started",
                "interval_minutes": self.interval_minutes,
                "message": f"Scheduler active. Monitoring running every {self.interval_minutes} minute(s).",
            }

    def stop(self) -> Dict[str, Any]:
        """Stop and pause all scheduled jobs."""
        with self._lock:
            if not self.is_running:
                return {"status": "not_running", "message": "Scheduler is not currently running."}

            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                # Re-instantiate scheduler so it can be restarted later
                self.scheduler = BackgroundScheduler(daemon=True)

            self.is_running = False
            logger.info("Background scheduler stopped.")
            return {"status": "stopped", "message": "Scheduler successfully paused."}

    def trigger_now(self) -> Dict[str, Any]:
        """Trigger an immediate manual monitoring evaluation."""
        logger.info("Manual monitoring trigger requested.")
        return self._wrapper_monitoring()

    def get_status(self) -> Dict[str, Any]:
        """Retrieve current scheduler state, job execution history, and next run times."""
        next_run = None
        if self.is_running and self.scheduler.running:
            job = self.scheduler.get_job("job_monitoring_rules")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        return {
            "is_running": self.is_running and self.scheduler.running,
            "interval_minutes": self.interval_minutes,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_status": self.last_run_status,
            "last_run_summary": self.last_run_summary,
            "next_scheduled_run": next_run,
            "history_count": len(self.job_history),
            "recent_history": list(reversed(self.job_history[-10:])),
        }

    def _wrapper_monitoring(self) -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.last_run_time = now
        try:
            summary = run_scheduled_monitoring()
            self.last_run_status = "Success"
            self.last_run_summary = summary
            entry = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "job": "Monitoring Rules Evaluation",
                "status": "Success",
                "details": f"Created: {summary.get('new_alerts_created', 0)}, Refreshed: {summary.get('existing_alerts_refreshed', 0)}",
            }
            self.job_history.append(entry)
            return summary
        except Exception as e:
            self.last_run_status = "Failed"
            self.last_run_summary = {"error": str(e)}
            entry = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "job": "Monitoring Rules Evaluation",
                "status": "Failed",
                "details": str(e),
            }
            self.job_history.append(entry)
            logger.error(f"Scheduled monitoring run failed: {e}")
            return {"error": str(e)}

    def _wrapper_daily_report(self) -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        try:
            res = run_scheduled_daily_report()
            entry = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "job": "Daily Performance Report",
                "status": "Success",
                "details": f"Generated Report ID #{res.get('id')}",
            }
            self.job_history.append(entry)
            return res
        except Exception as e:
            entry = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "job": "Daily Performance Report",
                "status": "Failed",
                "details": str(e),
            }
            self.job_history.append(entry)
            return {"error": str(e)}


# Global singleton instance
scheduler_service = MonitoringScheduler()
