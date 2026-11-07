import logging
import sys
from pathlib import Path

LOGGER_NAME = "invoice_processor"
_HANDLER_MARKER = "_invoice_processor_handler"


def configure_logging(
    log_level: str | int = "INFO",
    log_file: str | Path = "logs/processing.log",
) -> logging.Logger:
    """
    Configure console and file logging for the invoice processor.

    Calling this function repeatedly replaces the handlers previously
    configured by this module instead of adding duplicates.
    """

    if isinstance(log_level, str):
        resolved_level = logging.getLevelName(log_level.upper())

        if not isinstance(resolved_level, int):
            raise ValueError(f"Invalid logging level: {log_level}")

        log_level = resolved_level

    if not isinstance(log_level, int) or log_level < 0:
        raise ValueError(f"Invalid logging level: {log_level}")

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(log_level)
    logger.propagate = False

    # Remove existing handlers to prevent duplicate logging.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _HANDLER_MARKER, True)

    # File handler.
    file_handler = logging.FileHandler(
        log_path,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    setattr(file_handler, _HANDLER_MARKER, True)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger