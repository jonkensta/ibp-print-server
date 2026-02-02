import logging
import os
import re
import tempfile
import time

import cups
import pyudev
from PIL import Image

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

        Reads the default PageSize from the printer's PPD file.
        Returns (width, height) in pixels at the given DPI, as reported by
        the PPD (no orientation swap).
        """
        try:
            ppd_file = self._conn.getPPD(printer_name)
        except cups.IPPError as e:
            logger.error(f"Failed to get PPD for {printer_name}: {e}")
            raise PrintFailedError(f"Cannot get PPD: {e}") from e

        try:
            ppd = cups.PPD(ppd_file)
            ppd.markDefaults()
            option = ppd.findOption("PageSize")
            if not option:
                raise PrintFailedError("No PageSize option in PPD")

            choice = option.defchoice
        finally:
            os.unlink(ppd_file)

        # PPD PageSize choices use "wNNhNN" format (points) or
        # "Custom.WxHin" / "Custom.WxHmm" for custom sizes.
        match = re.match(r"w(\d+)h(\d+)", choice)
        if match:
            w_pt = float(match.group(1))
            h_pt = float(match.group(2))
        else:
            custom = re.match(r"Custom\.(\d+\.?\d*)x(\d+\.?\d*)(in|mm|cm)?", choice)
            if not custom:
                raise PrintFailedError(
                    f"Cannot parse PageSize from PPD choice: {choice}"
                )
            w_val = float(custom.group(1))
            h_val = float(custom.group(2))
            unit = custom.group(3) or "pt"
            if unit == "in":
                w_pt = w_val * 72
                h_pt = h_val * 72
            elif unit == "mm":
                w_pt = w_val * 72 / 25.4
                h_pt = h_val * 72 / 25.4
            elif unit == "cm":
                w_pt = w_val * 72 / 2.54
                h_pt = h_val * 72 / 2.54
            else:
                w_pt = w_val
                h_pt = h_val

        w_px = int(w_pt / 72 * dpi)
        h_px = int(h_pt / 72 * dpi)

        logger.info(f"Label size for {printer_name}: {choice} -> {w_px}x{h_px}px")
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

        cups_w, cups_h = self.get_label_size(printers[0])
        render_w = max(cups_w, cups_h)
        render_h = min(cups_w, cups_h)
        rendered = render(label, (render_w, render_h))

        if cups_w < cups_h:
            rendered = rendered.transpose(Image.Transpose.ROTATE_90)

        with tempfile.NamedTemporaryFile(suffix=".png") as fp:
            rendered.save(fp, dpi=(300, 300))
            fp.flush()
            self._print_file(fp.name)
