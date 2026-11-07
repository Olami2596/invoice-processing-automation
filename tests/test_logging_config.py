import logging

import pytest

from src.logging_config import LOGGER_NAME, configure_logging


def test_configure_logging_creates_log_file(tmp_path):
    log_file = tmp_path / "logs" / "processing.log"

    logger = configure_logging(log_file=log_file)
    logger.info("Invoice processing started")

    for handler in logger.handlers:
        handler.flush()

    assert log_file.exists()
    assert "Invoice processing started" in log_file.read_text(encoding="utf-8")


def test_configure_logging_creates_console_handler(tmp_path, capsys):
    logger = configure_logging(log_file=tmp_path / "processing.log")

    logger.info("Invoice processing started")

    captured = capsys.readouterr()
    assert "Invoice processing started" in captured.err


def test_configure_logging_adds_two_handlers(tmp_path):
    logger = configure_logging(log_file=tmp_path / "processing.log")

    assert len(logger.handlers) == 2


def test_configure_logging_does_not_duplicate_handlers(tmp_path):
    log_file = tmp_path / "processing.log"

    logger = configure_logging(log_file=log_file)
    logger.info("First processing event")

    logger = configure_logging(log_file=log_file)
    logger.info("Second processing event")

    for handler in logger.handlers:
        handler.flush()

    assert len(logger.handlers) == 2

    contents = log_file.read_text(encoding="utf-8")
    assert contents.count("First processing event") == 1
    assert contents.count("Second processing event") == 1


def test_configure_logging_sets_log_level(tmp_path):
    logger = configure_logging(
        log_level="WARNING",
        log_file=tmp_path / "processing.log",
    )

    assert logger.level == logging.WARNING


def test_configure_logging_accepts_numeric_log_level(tmp_path):
    logger = configure_logging(
        log_level=logging.DEBUG,
        log_file=tmp_path / "processing.log",
    )

    assert logger.level == logging.DEBUG


def test_configure_logging_rejects_invalid_log_level(tmp_path):
    with pytest.raises(ValueError):
        configure_logging(
            log_level="INVALID",
            log_file=tmp_path / "processing.log",
        )


def test_logger_uses_expected_name(tmp_path):
    logger = configure_logging(log_file=tmp_path / "processing.log")

    assert logger.name == LOGGER_NAME


def test_debug_messages_are_filtered_at_info_level(tmp_path):
    log_file = tmp_path / "processing.log"

    logger = configure_logging(
        log_level="INFO",
        log_file=log_file,
    )

    logger.debug("Debug diagnostic message")
    logger.info("Normal processing message")

    for handler in logger.handlers:
        handler.flush()

    contents = log_file.read_text(encoding="utf-8")

    assert "Debug diagnostic message" not in contents
    assert "Normal processing message" in contents