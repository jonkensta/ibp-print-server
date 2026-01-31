import logging
import tempfile
import time
from urllib.parse import parse_qs, urlparse

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

    def __init__(self, cache_duration: float = 30.0) -> None:
        self._conn = cups.Connection()
        self._context = pyudev.Context()
        self._cache_duration = cache_duration
        self._cached_printers: list[str] = []
        self._last_discovery = 0.0

    def get_available_printers(self) -> list[str]:
        """
        Returns a list of printer names that are both configured in CUPS and
        physically connected via USB. Results are cached.
        """
        now = time.time()
        if now - self._last_discovery < self._cache_duration:
            return self._cached_printers

        try:
            attributes = self._conn.getPrinters()
        except cups.IPPError as e:
            logger.error(f"Failed to get printers from CUPS: {e}")
            return []

        printers = attributes.keys()

        # Get all USB devices from udev
        usb_devices = list(self._context.list_devices(subsystem="usb"))

        plugged_in_serials = set()
        for device in usb_devices:
            # Try ID_SERIAL_SHORT first, then ID_SERIAL
            serial = device.properties.get("ID_SERIAL_SHORT")
            if not serial:
                serial = device.properties.get("ID_SERIAL")

            if serial:
                plugged_in_serials.add(serial)

        def is_plugged_in(printer_name: str) -> bool:
            uri = attributes[printer_name].get("device-uri", "")
            try:
                parsed = urlparse(uri)
                query = parse_qs(parsed.query)
                serial_list = query.get("serial")
                if not serial_list:
                    return False

                printer_serial = serial_list[0]
                return printer_serial in plugged_in_serials
            except (ValueError, IndexError, AttributeError):
                logger.debug(
                    f"Could not parse serial for {printer_name} with URI {uri}"
                )
                return False

        self._cached_printers = list(filter(is_plugged_in, printers))
        self._last_discovery = now
        return self._cached_printers

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
            self._last_discovery = 0.0
            logger.warning("No available printers found.")
            raise PrintFailedError("No available printers found")

        for printer in printers:
            try:
                self._try_print_file_on_printer(name, printer)
            except PrintFailedError:
                self._last_discovery = 0.0
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
        # Exceptions from render or _print_file will propagate up
        rendered = render(label)
        with tempfile.NamedTemporaryFile(suffix=".png") as fp:
            rendered.save(fp)
            fp.flush()
            self._print_file(fp.name)
