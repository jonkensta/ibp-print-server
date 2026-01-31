import time
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from print_server.printer import Printer, PrintFailedError


@pytest.fixture  # type: ignore[untyped-decorator]
def mock_cups() -> Generator[Any, None, None]:
    with patch("print_server.printer.cups.Connection") as mock:
        yield mock


@pytest.fixture  # type: ignore[untyped-decorator]
def mock_udev() -> Generator[Any, None, None]:
    with patch("print_server.printer.pyudev.Context") as mock:
        yield mock


def test_print_timeout(mock_cups: Any, mock_udev: Any) -> None:
    # Setup mocks
    conn_instance = mock_cups.return_value
    conn_instance.printFile.return_value = 123  # Job ID

    # Simulate job always being "processing" (state 5)
    conn_instance.getJobAttributes.return_value = {"job-state": 5}

    printer = Printer()

    # Test with very short timeout
    start = time.time()
    with pytest.raises(PrintFailedError, match="Job timed out"):
        printer._try_print_file_on_printer(
            "test_file", "Test_Printer", poll_period=0.01, timeout=0.1
        )
    duration = time.time() - start

    # Ensure it didn't wait forever, but at least the timeout
    assert duration >= 0.1
    assert duration < 1.0  # Should be reasonably close to 0.1


def test_print_success(mock_cups: Any, mock_udev: Any) -> None:
    conn_instance = mock_cups.return_value
    conn_instance.printFile.return_value = 123

    # Simulate pending -> processing -> completed
    # job states: 3=pending, 5=processing, 9=completed
    conn_instance.getJobAttributes.side_effect = [
        {"job-state": 3},
        {"job-state": 5},
        {"job-state": 9},
        {"job-state": 9},
    ]

    printer = Printer()
    printer._try_print_file_on_printer(
        "test_file", "Test_Printer", poll_period=0.01, timeout=1.0
    )

    # Should complete without error
