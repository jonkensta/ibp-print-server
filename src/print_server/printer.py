import time
import logging
import tempfile
from typing import Generator, Optional, Any
from urllib.parse import parse_qs, urlparse

import cups
import pyudev
from .renderer import render


logger = logging.getLogger(__name__)


class PrintFailed(Exception):
    pass


class Printer(object):

    _job_states = {
        3: 'pending',
        4: 'pending-held',
        5: 'processing',
        6: 'processing-stopped',
        7: 'canceled',
        8: 'aborted',
        9: 'completed',
    }

    def __init__(self):
        self._conn = cups.Connection()
        self._context = pyudev.Context()

    @property
    def _printers(self) -> Generator[str, None, None]:
        """
        Yields printer names that are both configured in CUPS and physically connected via USB.
        Discovery logic matches the serial number from CUPS configuration to USB devices.
        """
        try:
            attributes = self._conn.getPrinters()
        except Exception as e:
            logger.error(f"Failed to get printers from CUPS: {e}")
            return

        printers = attributes.keys()
        
        # Generalize: We want all USB printers.
        # list_devices(subsystem='usb') returns all USB devices.
        # We look for devices that expose a printer interface or just check all USB devices for matching serials.
        # CUPS 'device-uri' for USB usually looks like: usb://Make/Model?serial=...
        
        # Get all USB devices from udev
        usb_devices = list(self._context.list_devices(subsystem='usb'))
        
        plugged_in_serials = set()
        for device in usb_devices:
            # Try ID_SERIAL_SHORT first, then ID_SERIAL
            serial = device.properties.get('ID_SERIAL_SHORT')
            if not serial:
                 serial = device.properties.get('ID_SERIAL')
            
            if serial:
                plugged_in_serials.add(serial)

        def is_plugged_in(printer_name):
            uri = attributes[printer_name].get('device-uri', '')
            # Parse serial from URI
            # Example: usb://DYMO/LabelWriter%20450?serial=01010112345600
            try:
                parsed = urlparse(uri)
                query = parse_qs(parsed.query)
                serial_list = query.get('serial')
                if not serial_list:
                    # Some backends might not put serial in query, or format differs.
                    # For USB printers, it's standard.
                    return False
                
                printer_serial = serial_list[0]
                return printer_serial in plugged_in_serials
            except Exception:
                logger.debug(f"Could not parse serial for printer {printer_name} with URI {uri}")
                return False

        # Filter printers that are plugged in
        available_printers = filter(is_plugged_in, printers)

        for printer in available_printers:
            yield printer

    def _try_print_file_on_printer(self, name: str, printer: str, poll_period: float = 0.25):
        logger.info(f"Attempting to print file {name} on printer {printer}")
        try:
            job_id = self._conn.printFile(printer, name, name, dict())
            logger.info(f"Job submitted: ID {job_id}")
        except cups.IPPError as e:
            logger.error(f"IPPError submitting job to {printer}: {e}")
            raise PrintFailed from e

        def get_job_state(id_):
            try:
                attrs = self._conn.getJobAttributes(id_)
                job_state_enum = attrs['job-state']
                return Printer._job_states.get(job_state_enum, 'unknown')
            except cups.IPPError:
                 return 'unknown'

        def job_is_pending(id_):
            return (get_job_state(id_) in {'pending', 'processing'})

        def job_succeeded(id_):
            return (get_job_state(id_) == 'completed')

        while job_is_pending(job_id):
            time.sleep(float(poll_period))

        if not job_succeeded(job_id):
            final_state = get_job_state(job_id)
            logger.error(f"Print job {job_id} failed. Final state: {final_state}")
            raise PrintFailed
        
        logger.info(f"Print job {job_id} completed successfully.")

    def _print_file(self, name: str):
        printers = list(self._printers)
        if not printers:
            logger.warning("No available printers found.")
            return

        for printer in printers:
            try:
                self._try_print_file_on_printer(name, printer)
            except PrintFailed:
                logger.warning(f"Failed to print on {printer}, trying next...")
                continue
            else:
                return # Success
        
        logger.error("Failed to print on all available printers.")

    def print_label(self, label: dict):
        logger.info(f"Rendering label for package_id: {label.get('package_id', 'unknown')}")
        try:
            rendered = render(label)
            with tempfile.NamedTemporaryFile(suffix='.png') as fp:
                rendered.save(fp)
                fp.flush()
                self._print_file(fp.name)
        except Exception as e:
            logger.error(f"Error in print_label pipeline: {e}")
