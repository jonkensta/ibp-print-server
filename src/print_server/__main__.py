import argparse
import json
import logging
import signal
import sys
from types import FrameType

from .printer import Printer
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
        server = LabelServer(("", args.port))

        # Signal handling for graceful shutdown
        def signal_handler(sig: int, frame: FrameType | None) -> None:
            logger.info("Received signal, shutting down...")
            server.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        server.start()

        logger.info("Server running. Waiting for jobs...")
        try:
            while True:
                # This loop pulls jobs from the server queue and prints them
                label = server.get_job()
                if label:
                    try:
                        printer.print_label(label)
                    except Exception as e:
                        logger.error(f"Failed to print label from queue: {e}")
        except KeyboardInterrupt:
            # Should be handled by signal_handler, but just in case
            server.shutdown()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
