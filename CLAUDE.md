# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`halpid` is a power monitor and watchdog daemon for the HALPI2 Raspberry Pi Compute Module 5 based boat computer. The daemon provides blackout reporting, watchdog functionality, RTC sleep mode, and USB port power cycling capabilities.

## Development Commands

This project uses `uv` for dependency management and a custom `./run` script for common tasks:

### Essential Commands
- `./run install` - Install project dependencies and create virtual environment
- `./run lint` - Run linting (ruff check/format + mypy type checking)
- `./run format` - Auto-format code with ruff
- `./run mypy` - Run type checking only
- `./run clean` - Remove temporary files and caches

### Testing
- `uv run pytest` - Run all tests (uses pytest configuration from pyproject.toml)
- `uv run pytest tests/test_example/test_hello.py` - Run specific test file
- `uv run pytest -k test_name` - Run specific test by name

### Package Management
- `uv sync` - Install dependencies from lock file
- `uv lock` - Update lock file
- `./run update-dev-deps` - Update development dependencies

### Debian Packaging
- `./run build-debian` - Build Debian package
- `./run debtools-build` - Build using Docker container

## Architecture

### Core Components

**Entry Points** (`src/halpi/__main__.py`):
- `halpi` - CLI command interface
- `halpid` - Daemon service

**Main Modules**:
- `daemon.py` - Main daemon service with asyncio event loop, HTTP server, and I2C device communication
- `cli.py` - Typer-based CLI interface that communicates with daemon via Unix socket HTTP API
- `i2c.py` - I2C device communication layer for HALPI2 hardware
- `server.py` - HTTP server providing REST API for device status and control
- `state_machine.py` - Power management state machine handling blackout detection and shutdown logic

**Configuration**:
- Default config location: `/etc/halpid/halpid.conf` 
- YAML format with dash-to-underscore key conversion
- Configurable blackout timing, voltage limits, and poweroff commands

### Communication Architecture
- Daemon runs HTTP server on Unix socket (`/run/halpid/halpid.sock`)
- CLI communicates with daemon via aiohttp UnixConnector
- I2C communication with HALPI2 controller on bus 1, address 0x48
- State machine handles power management events and triggers system shutdown

### Hardware Integration
- Uses `smbus2` for I2C communication with HALPI2 controller
- Monitors input voltage, supercap voltage, and power state
- Provides watchdog functionality (10-second timeout)
- Supports RTC-based wake scheduling and USB port power cycling

## Code Quality Tools

**Linting**: Ruff (pyflakes, pycodestyle, isort rules) with 88-character line length
**Type Checking**: MyPy with strict settings enabled
**Testing**: Pytest with coverage reporting
**Formatting**: Ruff formatter (replaces Black)

The project targets Python 3.11+ and follows modern Python practices with full type annotations.