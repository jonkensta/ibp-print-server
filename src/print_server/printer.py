import logging
import re
import tempfile
import time
from urllib.parse import urlparse

import cups
import pyudev

from .renderer import render

logger = logging.getLogger(__name__)


class PrintFailedError(Exception):
    pass


class Printer:
    _job_states = {
        3: "pending",
        4: "pending-held",
        5: "processing",
        6: "processing-stopped",
        7: "canceled",
        8: "aborted",
        9: "completed",
    }

    def __init__(
        self,
        preferred_printer: str | None = None,
    ) -> None:
        self._conn = cups.Connection()
        self._context = pyudev.Context()
        self._preferred_printer = preferred_printer

    def get_available_printers(self) -> list[str]:
        """
        Returns a list of printer names that are both configured in CUPS and
        physically connected via USB.
        """
        try:
            attributes = self._conn.getPrinters()
        except cups.IPPError as e:
            logger.error(f"Failed to get printers from CUPS: {e}")
            return []

        printers = attributes.keys()

        if self._preferred_printer:
            if self._preferred_printer in printers:
                return [self._preferred_printer]
            else:
                logger.warning(
                    f"Preferred printer '{self._preferred_printer}' not found in CUPS."
                )
                return []

        # Get (manufacturer, product) pairs from plugged-in USB devices
        plugged_in_devices: set[tuple[str, str]] = set()
        for device in self._context.list_devices(subsystem="usb"):
            manufacturer = device.attributes.get("manufacturer")
            product = device.attributes.get("product")
            if manufacturer and product:
                mfr = (
                    manufacturer.decode()
                    if isinstance(manufacturer, bytes)
                    else manufacturer
                )
                prod = product.decode() if isinstance(product, bytes) else product
                plugged_in_devices.add((mfr.lower(), prod.lower()))

        def is_plugged_in(printer_name: str) -> bool:
            uri = attributes[printer_name].get("device-uri", "")
            try:
                parsed = urlparse(uri)
                if parsed.scheme != "usb":
                    return False
                vendor = parsed.hostname or ""
                product = parsed.path.strip("/")
                return (vendor.lower(), product.lower()) in plugged_in_devices
            except (ValueError, AttributeError):
                logger.debug(f"Could not parse URI for {printer_name}: {uri}")
                return False

        return list(filter(is_plugged_in, printers))

    def get_label_size(self, printer_name: str, dpi: int = 300) -> tuple[int, int]:
        """Get label size in pixels for a printer's default media.

        Returns (width, height) in pixels at the given DPI.
        """
        try:
            attrs = self._conn.getPrinterAttributes(printer_name)
        except cups.IPPError as e:
            logger.error(f"Failed to get attributes for {printer_name}: {e}")
            raise PrintFailedError(f"Cannot query printer attributes: {e}") from e

        media = attrs.get("media-default", "")
        match = re.search(r"(\d+\.?\d*)x(\d+\.?\d*)mm", media)
        if not match:
            raise PrintFailedError(f"Cannot parse media size from: {media}")

        w_mm = float(match.group(1))
        h_mm = float(match.group(2))

        w_px = int(w_mm / 25.4 * dpi)
        h_px = int(h_mm / 25.4 * dpi)

        # Ensure landscape orientation (width >= height)
        if w_px < h_px:
            w_px, h_px = h_px, w_px

        logger.info(
            f"Label size for {printer_name}: {w_mm}x{h_mm}mm -> {w_px}x{h_px}px"
        )
        return w_px, h_px

    def _try_print_file_on_printer(
        self,
        name: str,
        printer: str,
        poll_period: float = 0.25,
        timeout: float = 60.0,
    ) -> None:
        logger.info(f"Attempting to print file {name} on printer {printer}")
        try:
            job_id = self._conn.printFile(printer, name, name, dict())
            logger.info(f"Job submitted: ID {job_id}")
        except cups.IPPError as e:
            logger.error(f"IPPError submitting job to {printer}: {e}")
            raise PrintFailedError from e

        def get_job_state(id_: int) -> str:
            try:
                attrs = self._conn.getJobAttributes(id_)
                job_state_enum = attrs["job-state"]
                return Printer._job_states.get(job_state_enum, "unknown")
            except cups.IPPError:
                return "unknown"

        def job_is_pending(id_: int) -> bool:
            return get_job_state(id_) in {"pending", "processing"}

        def job_succeeded(id_: int) -> bool:
            return get_job_state(id_) == "completed"

        start_time = time.time()
        while job_is_pending(job_id):
            if time.time() - start_time > timeout:
                logger.error(f"Print job {job_id} on {printer} timed out")
                raise PrintFailedError("Job timed out")
            time.sleep(float(poll_period))

        if not job_succeeded(job_id):
            final_state = get_job_state(job_id)
            logger.error(f"Print job {job_id} failed. Final state: {final_state}")
            raise PrintFailedError

        logger.info(f"Print job {job_id} completed successfully.")

    def _print_file(self, name: str) -> None:
        printers = self.get_available_printers()
        if not printers:
            logger.warning("No available printers found.")
            raise PrintFailedError("No available printers found")

        for printer in printers:
            try:
                self._try_print_file_on_printer(name, printer)
            except PrintFailedError:
                logger.warning(f"Failed to print on {printer}, trying next...")
                continue
            else:
                return  # Success

        logger.error("Failed to print on all available printers.")
        raise PrintFailedError("Failed to print on all available printers")

    def print_label(self, label: dict[str, str]) -> None:
        logger.info(
            f"Rendering label for package_id: {label.get('package_id', 'unknown')}"
        )
        printers = self.get_available_printers()
        if not printers:
            raise PrintFailedError("No available printers found")

        size = self.get_label_size(printers[0])
        rendered = render(label, size)
        with tempfile.NamedTemporaryFile(suffix=".png") as fp:
            rendered.save(fp, dpi=(300, 300))
            fp.flush()
            self._print_file(fp.name)
