# Features Plan

## Goal
Add two new subcommands to the existing `print-server` CLI:
1.  `list`: Lists printers detected by the server (CUPS + USB verification).
2.  `test`: Prints a sample label to a specified or auto-detected printer.

## Usage
*   `uv run print-server list`
*   `uv run print-server test [--printer <name>]`

## Implementation Steps

### 1. Update `src/print_server/__main__.py`
*   Add a new subparser for `list`.
*   Add a new subparser for `test` with an optional `--printer` argument.

### 2. Implement `list` logic
*   Instantiate `Printer()`.
*   Call `get_available_printers()`.
*   Print the list of printer names to stdout.

### 3. Implement `test` logic
*   Instantiate `Printer(preferred_printer=args.printer)`.
*   Construct a dictionary with sample data (mocking the `label` format expected by `renderer.py`).
*   Call `printer.print_label(sample_label)`.
*   Handle and log success/failure.

### 4. Verify
*   Run `uv run print-server list` to see printers.
*   Run `uv run print-server test` to try printing a label.