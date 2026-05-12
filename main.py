import argparse
import time
import traceback
from datetime import datetime, timedelta
import multiprocessing

from src.agents.all_agents import ANALYSTS
from src.pipeline.extract import get_stock_data


def run_pipeline(
    portfolio: list[str],
    analysis: str = "risk",
    skip_analysis: bool = False,
) -> None:
    print("=== Step 1/2: Extract market data ===")
    for company in portfolio:
        try:
            get_stock_data(company)
        except Exception as e:
            print(f"❌ Error occurred while downloading data for {company}: {e}")

    if skip_analysis:
        print("=== Step 2/2 skipped: analysis disabled by --skip-analysis ===")
        return

    print("=== Step 2/2: Run analysis agent ===")
    try:
        if analysis not in ANALYSTS:
            print(f"❌ Unknown analysis agent '{analysis}'. Available: {list(ANALYSTS.keys())}")
            return

        print(f"Running agent: {analysis}")
        runner = ANALYSTS[analysis]
        result = runner()

        print("######################")
        print(result)
        print("=== Agent finished ===")
    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
        traceback.print_exc()
        print("Tip: if message contains quota/rate-limit, check Gemini API limits and billing.")


def run_analysis_only(analysis: str) -> None:
    """Run only one analysis agent (used by worker processes)."""
    print(f"=== Analysis process started for: {analysis} ===")
    try:
        if analysis not in ANALYSTS:
            print(f"❌ Unknown analysis agent '{analysis}'. Available: {list(ANALYSTS.keys())}")
            return

        runner = ANALYSTS[analysis]
        result = runner()

        print(f"\n########## REPORT [{analysis}] ##########")
        print(result)
        print(f"######## END REPORT [{analysis}] ########\n")
    except Exception as e:
        print(f"❌ Agent '{analysis}' failed: {e}")
        traceback.print_exc()


def _parse_run_time(run_at: str) -> tuple[int, int]:
    try:
        hours, minutes = run_at.split(":")
        hour = int(hours)
        minute = int(minutes)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--run-at must be in HH:MM format, e.g. 12:00") from exc


def _seconds_until_next_run(hour: int, minute: int) -> tuple[float, datetime]:
    now = datetime.now()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run = next_run + timedelta(days=1)
    return (next_run - now).total_seconds(), next_run


def run_daily_scheduler(portfolio: list[str], analysis: str, skip_analysis: bool, run_at: str) -> None:
    hour, minute = _parse_run_time(run_at)
    print(f"🕛 Daily scheduler started. Local time target: {hour:02d}:{minute:02d}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            wait_seconds, next_run = _seconds_until_next_run(hour, minute)
            print(f"⏳ Next run at local time: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(wait_seconds)
            print("\n=== Scheduled run started ===")
            run_pipeline(portfolio=portfolio, analysis=analysis, skip_analysis=skip_analysis)
            print("=== Scheduled run finished ===\n")
    except KeyboardInterrupt:
        print("\n🛑 Scheduler stopped by user.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the finance pipeline.")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "TSLA", "MSFT", "CDR.WA"],
        help="List of stock tickers to download (space-separated).",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Only download data and skip agent analysis.",
    )
    parser.add_argument(
        "--analysis",
        choices=["risk", "tech", "all"],
        default="all",
        help="Which analysis agent to run after downloading data. Use 'all' to run every registered agent.",
    )

    parser.add_argument(
        "--schedule-daily",
        action="store_true",
        help="Run continuously and trigger pipeline every day at local --run-at time.",
    )
    parser.add_argument(
        "--run-at",
        default="12:00",
        help="Local daily time in HH:MM format for --schedule-daily (default: 12:00).",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    processes = []
    print("Starting pipeline with the following configuration:")
    print(f"Tickers: {args.tickers}")

    # Determine which agents to run: either the one specified by --analysis
    # or all registered analysts when --analysis is not provided or set to 'all'.
    if args.analysis == "all":
        selected_agents = list(ANALYSTS.keys())
    elif args.analysis in ANALYSTS:
        selected_agents = [args.analysis]
    else:
        print(f"Warning: requested analysis '{args.analysis}' not found. Running all agents.")
        selected_agents = list(ANALYSTS.keys())

    print(f"Agents to run in parallel: {selected_agents}")

    if args.schedule_daily:
        run_daily_scheduler(
            portfolio=args.tickers,
            analysis=args.analysis,
            skip_analysis=args.skip_analysis,
            run_at=args.run_at,
        )
    else:
        print("=== Step 1/2: Extract market data (single pass) ===")
        for company in args.tickers:
            try:
                get_stock_data(company)
            except Exception as e:
                print(f"❌ Error occurred while downloading data for {company}: {e}")

        if args.skip_analysis:
            print("=== Step 2/2 skipped: analysis disabled by --skip-analysis ===")
            print("\nAll processes completed.")
            raise SystemExit(0)

        print("=== Step 2/2: Run selected analysis agents in parallel ===")
        # Spawn one process per selected analyst so they run concurrently.
        for agent_name in selected_agents:
            p = multiprocessing.Process(
                target=run_analysis_only,
                args=(agent_name,),
                name=f"agent-{agent_name}",
            )
            processes.append(p)
            p.start()
            # Stagger starts slightly to reduce burst rate against external APIs.
            time.sleep(1)

        # Wait for all processes to finish
        for p in processes:
            p.join()

        print("\nAll processes completed.")

    # Single-run fallback: if no parallel agents are registered, run once.
    if not ANALYSTS:
        run_pipeline(portfolio=args.tickers, analysis=args.analysis, skip_analysis=args.skip_analysis)
