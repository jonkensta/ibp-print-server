import io
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image

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


def make_png(size: tuple[int, int] = (100, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", size, color=(255,)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_print_image_invalid_data(mock_cups: Any, mock_udev: Any) -> None:
    printer = Printer()
    with pytest.raises(PrintFailedError, match="Invalid image data"):
        printer.print_image(b"this is not an image")


def test_print_image_no_printers(mock_cups: Any, mock_udev: Any) -> None:
    printer = Printer()
    with (
        patch.object(printer, "get_available_printers", return_value=[]),
        pytest.raises(PrintFailedError, match="No available printers"),
    ):
        printer.print_image(make_png())


def test_print_image_scales_and_rotates_to_media(
    mock_cups: Any, mock_udev: Any
) -> None:
    printer = Printer()
    printed: dict[str, Any] = {}

    def capture(name: str) -> None:
        with Image.open(name) as image:
            printed["size"] = image.size

    with (
        patch.object(
            printer, "get_available_printers", return_value=["Test_0a5f:0001"]
        ),
        # Portrait media: 378x1004 (32mm x 85mm at 300 DPI)
        patch.object(printer, "get_label_size", return_value=(378, 1004)),
        patch.object(printer, "_print_file", side_effect=capture),
    ):
        printer.print_image(make_png((100, 40)))

    # Rendered landscape at 1004x378, then rotated to match portrait media.
    assert printed["size"] == (378, 1004)


def test_print_image_landscape_media_no_rotation(
    mock_cups: Any, mock_udev: Any
) -> None:
    printer = Printer()
    printed: dict[str, Any] = {}

    def capture(name: str) -> None:
        with Image.open(name) as image:
            printed["size"] = image.size

    with (
        patch.object(
            printer, "get_available_printers", return_value=["Test_0a5f:0001"]
        ),
        patch.object(printer, "get_label_size", return_value=(1004, 378)),
        patch.object(printer, "_print_file", side_effect=capture),
    ):
        printer.print_image(make_png((1004, 378)))

    assert printed["size"] == (1004, 378)
