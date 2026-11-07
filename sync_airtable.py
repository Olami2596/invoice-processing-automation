import argparse
import logging

from src.logging_config import configure_logging, LOGGER_NAME
from src.storage import initialise_database
from src.airtable_worker import process_pending_airtable_sync_jobs


logger = logging.getLogger(LOGGER_NAME)


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize pending invoice records with Airtable."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of pending jobs to process (default: 100).",
    )

    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than zero.")

    configure_logging()

    logger.info("Starting Airtable synchronization worker.")

    initialise_database()

    summary = process_pending_airtable_sync_jobs(
        limit=args.limit
    )

    print("\nAirtable Synchronization Summary")
    print("--------------------------------")
    print(f"Total jobs:  {summary['total']}")
    print(f"Succeeded:   {summary['succeeded']}")
    print(f"Failed:      {summary['failed']}")
    print(f"Skipped:     {summary['skipped']}")

    logger.info("Airtable synchronization worker finished.")


if __name__ == "__main__":
    main()