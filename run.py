"""Command line entry point.

  python run.py --mock              # demo run with synthetic data, no API keys
  python run.py --mock --reset      # wipe the demo DB first
  python run.py                     # live run (needs ADZUNA keys in .env)
"""
import argparse

from app import config, db
from app.graph import run_pipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Fresher Job Market Intelligence Agent")
    ap.add_argument("--mock", action="store_true", help="use synthetic demo data (no API keys needed)")
    ap.add_argument("--reset", action="store_true", help="delete the selected database before running")
    ap.add_argument("--no-llm", action="store_true", help="skip LLM steps even if ANTHROPIC_API_KEY is set")
    ap.add_argument("--no-news", action="store_true", help="skip the news-context step")
    ap.add_argument("--config", default=None, help="path to an alternative config.yaml")
    args = ap.parse_args()

    cfg = config.load_config(args.config)
    config.use_db(demo=args.mock)
    if args.reset:
        db.reset_db()
    state = run_pipeline(cfg, mock=args.mock, use_llm=not args.no_llm, use_news=not args.no_news)
    print("\n" + "=" * 60 + "\n" + state["report_text"])


if __name__ == "__main__":
    main()
