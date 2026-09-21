"""Run the agent on a schedule (default: every day at 07:00 local time).

  python scheduler.py --hour 7 --minute 0
"""
import argparse

from apscheduler.schedulers.blocking import BlockingScheduler

from app import config
from app.graph import run_pipeline


def job() -> None:
    run_pipeline(config.load_config(), mock=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hour", type=int, default=7)
    ap.add_argument("--minute", type=int, default=0)
    a = ap.parse_args()
    sched = BlockingScheduler()
    sched.add_job(job, "cron", hour=a.hour, minute=a.minute)
    print(f"Scheduled daily run at {a.hour:02d}:{a.minute:02d}. Ctrl+C to stop.")
    sched.start()
