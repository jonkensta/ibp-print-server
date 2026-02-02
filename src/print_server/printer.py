import logging
import re
import tempfile
import time

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

        Printer names must end with ``_VVVV:PPPP`` where VVVV and PPPP are
        the hexadecimal USB vendor and product IDs (e.g.
        ``iDPRT_SP310_0a5f:0001``).
        """
        try:
            cups_printers = list(self._conn.getPrinters().keys())
        except cups.IPPError as e:
            logger.error(f"Failed to get printers from CUPS: {e}")
            return []

        if self._preferred_printer:
            if self._preferred_printer in cups_printers:
                return [self._preferred_printer]
            logger.warning(
                f"Preferred printer '{self._preferred_printer}' not found in CUPS."
            )
            return []

        connected_ids: set[str] = set()
        for dev in self._context.list_devices(subsystem="usb"):
            vid = dev.attributes.get("idVendor")
            pid = dev.attributes.get("idProduct")
            if vid and pid:
                vid_s = vid.decode() if isinstance(vid, bytes) else vid
                pid_s = pid.decode() if isinstance(pid, bytes) else pid
                connected_ids.add(f"{vid_s}:{pid_s}".lower())

        def is_connected(name: str) -> bool:
            match = re.search(r"_([0-9a-fA-F]{4}:[0-9a-fA-F]{4})$", name)
            if not match:
                logger.debug(f"Printer '{name}' has no USB ID suffix")
                return False
            return match.group(1).lower() in connected_ids

        return [p for p in cups_printers if is_connected(p)]

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
