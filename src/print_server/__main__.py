import argparse
import json
import logging
import queue
import signal
import sys
from types import FrameType

from .printer import Printer, PrintFailedError
from .server import LabelServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run label-printer application server"""

    parser = argparse.ArgumentParser(description=main.__doc__)
    subparsers = parser.add_subparsers(title="commands", dest="command")

    # Print Command
    print_parser = subparsers.add_parser("print")
    print_parser.add_argument("infilepath")

    # Server Command
    server_parser = subparsers.add_parser("server")
    server_parser.add_argument("--port", type=int, default=40121)

    args = parser.parse_args()

    if args.command == "print":
        try:
            with open(args.infilepath) as infile:
                label = json.loads(infile.read())

            logger.info(f"Read label from {args.infilepath}")
            printer = Printer()
            printer.print_label(label)
        except Exception:
            logger.exception("Failed to run print command")
            sys.exit(1)

    elif args.command == "server":
        printer = Printer()
        # Pass the printer instance to the server
        server = LabelServer(("", args.port), printer)

        shutdown_requested = False

        # Signal handling for graceful shutdown
        def signal_handler(sig: int, frame: FrameType | None) -> None:
            nonlocal shutdown_requested
            logger.info("Received signal, initiating shutdown...")
            shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        server.start()

        logger.info("Server running. Waiting for jobs...")
        try:
            while not shutdown_requested:
                # This loop pulls jobs from the server queue and prints them
                try:
                    label = server.get_job(timeout=1.0)
                except queue.Empty:
                    continue

                if label:
                    try:
                        printer.print_label(label)
                    except PrintFailedError as e:
                        retries = label.get("_retries", 0)
                        if retries < 3:
                            label["_retries"] = retries + 1
                            logger.warning(
                                f"Print failed ({e}), retrying {label['_retries']}/3..."
                            )
                            server.put_job(label)
                        else:
                            logger.error(f"Print failed after 3 retries: {e}")
                    except Exception:
                        logger.exception("Unexpected error printing label")
        except KeyboardInterrupt:
            # Handle Ctrl+C if it bypasses signal handler
            # or happens during blocking calls
            logger.info("KeyboardInterrupt received.")
        finally:
            server.shutdown()
            logger.info("Shutdown complete.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
