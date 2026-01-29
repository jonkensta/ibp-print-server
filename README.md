# Print Server

A Python-based print server application for generating and printing labels with Code128 barcodes.

## Features

-   HTTP API for submitting print jobs.
-   Direct printing via CLI.
-   Auto-discovery of USB printers (via CUPS and udev).
-   Code128 barcode generation.
-   Label rendering using `Pillow`.

## Requirements

-   Python 3.12+
-   CUPS installed and running.
-   `libcups2-dev` (for `pycups` compilation).
-   `libudev-dev` (for `pyudev`).

## Installation

Using `uv`:

```bash
uv sync
```

## Usage

### Server Mode

Starts the HTTP server (default port 40121).

```bash
uv run print-server server --port 40121
```

### Print Mode

Prints a single label from a JSON file.

```bash
uv run print-server print path/to/label.json
```

## Development

Run linting and tests:

```bash
uv run pre-commit run --all-files
uv run pytest
```
