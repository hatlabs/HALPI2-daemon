# HALPI2 Daemon

[![Dependencies Status](https://img.shields.io/badge/dependencies-up%20to%20date-brightgreen.svg)](https://github.com/hatlabs/halpid/pulls?utf8=%E2%9C%93&q=is%3Apr%20author%3Aapp%2Fdependabot)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: bandit](https://img.shields.io/badge/security-bandit-green.svg)](https://github.com/PyCQA/bandit)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/hatlabs/halpid/blob/master/.pre-commit-config.yaml)
[![Semantic Versions](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--versions-e10079.svg)](https://github.com/hatlabs/halpid/releases)

## Introduction

[HALPI2](https://shop.hatlabs.fi/products/halpi2)
is a Raspberry Pi Compute Module 5 based boat computer. `halpid` is a power monitor and watchdog service for HALPI2. It communicates with the HALPI2 controller, providing the "smart" aspects of the operation. Supported features include:

- Blackout reporting if input voltage falls below a defined threshold
- Triggering of device shutdown if power isn't restored
- Supercap voltage reporting
- Watchdog functionality: if the HALPI2 receives no communication for 10 seconds, the controller will hard reset the device.
- RTC sleep mode: the onboard real-time clock can be set to boot the Raspberry Pi at a specific time. This is useful for battery powered devices that should perform scheduled tasks such as boat battery and bilge level monitoring.
- Power-cycling the USB ports: the HALPI2 can power-cycle the USB ports, which is useful if a connected device becomes unresponsive.

The main use case for the service software is to have the Raspberry Pi operating system shut down once the power is cut. This prevents potential file system corruption without having to shut down the device manually.

## Installation

End-users should install the `halpid` package using `apt`:

```bash
sudo apt install halpid
```

The APT repository is available at [https://apt.hatlabs.fi](https://apt.hatlabs.fi).

When developing, you can install the source code by cloning the repository and running:

```bash
./run install
```

This will install `halpid` and its dependencies in a virtual environment, allowing you to run the daemon and test it.


## Configuration

The `halpid` daemon can be configured using a configuration file.
The default configuration file location is `/etc/halpid/halpid.conf`.

For example, if you want to change the blackout time limit to 10 seconds andthe poweroff command to `/home/pi/bin/custom-poweroff`, you can edit the configuration file as follows:

    blackout-time-limit: 10
    poweroff: /home/pi/bin/custom-poweroff

## HALPI2 Documentation

For a more detailed HALPI2 documentation, please visit the [documentation website](https://docs.hatlabs.fi/halpi2).

## Getting the hardware

HALPI2 devices are available for purchase at [shop.hatlabs.fi](https://shop.hatlabs.fi/).

## Usage

The `halpi` command-line interface provides access to device status, configuration, and control:

### Basic Commands

- `halpi status` - Show device status and measurements
- `halpi version` - Show version information
- `halpi get <key>` - Get specific measurement or value
- `halpi config` - Show all configuration settings
- `halpi config <key>` - Get specific configuration value
- `halpi config <key> <value>` - Set configuration value
- `halpi shutdown` - Shutdown the device
- `halpi shutdown --standby --time <time>` - Enter standby mode
- `halpi flash <firmware-file>` - Update device firmware

### Examples

```bash
# Check device status
halpi status

# Get input voltage
halpi get V_in

# Set watchdog timeout to 30 seconds
halpi config watchdog_timeout 30

# Schedule standby wakeup in 3600 seconds
halpi shutdown --standby --time 3600
```
