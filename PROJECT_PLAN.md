# Project Improvement Plan

## Phase 1: Infrastructure & Setup
- [ ] **Git Initialization**:
    - [ ] Initialize git repository.
    - [ ] Create `.gitignore` (Python specific).
- [ ] **Dependency Management (uv)**:
    - [ ] Run `uv init`.
    - [ ] Add dependencies: `pycups`, `pyudev`, `python-barcode`, `Pillow`.
    - [ ] Add dev dependencies: `ruff`, `mypy`, `pre-commit`, `pytest`.
- [ ] **Project Structure**:
    - [ ] Create `src/print_server/` directory.
    - [ ] Move `DejaVuSansMono.ttf` into `src/print_server/`.
    - [ ] Configure `pyproject.toml` with entry points (`print-server`).
- [ ] **Refactoring (Split `label.py`)**:
    - [ ] `src/print_server/__main__.py`: CLI entry point (`main`, `argparse`).
    - [ ] `src/print_server/server.py`: HTTP server (`Generator` class, request handling).
    - [ ] `src/print_server/printer.py`: Printer discovery & CUPS logic (`Printer` class).
    - [ ] `src/print_server/renderer.py`: Image rendering, barcode, font logic.

## Phase 2: Logic Enhancements
- [ ] **Printer Discovery**:
    - [ ] Remove hardcoded "DYMO" checks.
    - [ ] Match any USB printer configured in CUPS and present via udev.
- [ ] **Rendering Updates**:
    - [ ] Replace `Code39` with `Code128`.
    - [ ] Fix Pillow deprecation: Replace `font.getsize()` with `font.getbbox()` or `font.getlength()`.
    - [ ] Update font loading to use `importlib.resources` or relative paths.
- [ ] **Server Improvements**:
    - [ ] **Input Validation**: Return HTTP 400 on JSON parse failure.
    - [ ] **CORS**: Restrict to `http://ibp-server.local` and `https://ibp-server.local`. Add `Access-Control-Allow-Methods/Headers` to OPTIONS.
    - [ ] **Logging**: Replace silent failures with proper logging (requests, discovery, errors).
    - [ ] **Graceful Shutdown**: Handle SIGTERM/SIGINT.
    - [ ] **Health Check**: Add GET endpoint returning printer status.

## Phase 3: Quality Assurance & Tooling
- [ ] **Configuration**:
    - [ ] Configure `ruff` (linting/formatting) in `pyproject.toml`.
    - [ ] Configure `mypy` in `pyproject.toml`.
- [ ] **Git Hooks**:
    - [ ] Setup `.pre-commit-config.yaml`.
- [ ] **Testing**:
    - [ ] Add unit tests for `renderer.py` (`render`, `fit_font`, `fit_text`).

## Phase 4: Final Steps
- [ ] **Verification**: Run manual tests of `server` and `print` commands.
- [ ] **GitHub**: (User action) Create remote repo and push.