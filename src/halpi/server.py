# Implement an aiohttp server to handle requests from the client.
# The server listens on a unix socket, and the client connects to it.

import asyncio
import datetime
import numbers
import os
import pathlib

import dateparser
from aiohttp import web
from loguru import logger

import halpi.const
import halpi.i2c


class RouteHandlers:
    def __init__(self, halpi_device: halpi.i2c.HALPIDevice, poweroff_command: str):
        self.halpi_device = halpi_device
        self.poweroff_command = poweroff_command

    async def get_root(self, request: web.Request) -> web.Response:
        return web.Response(text="This is halpid!\n")

    async def get_version(self, request: web.Request) -> web.Response:
        """Get the daemon version."""
        daemon_version = halpi.const.VERSION

        response = {
            "daemon_version": daemon_version,
        }

        return web.json_response(response)

    async def post_shutdown(self, request: web.Request) -> web.Response:
        """Receive a shutdown request from the client."""
        self.halpi_device.request_shutdown()  # Inform the device about the shutdown
        # call the system shutdown command
        logger.info(f"Executing {self.poweroff_command}")
        asyncio.create_task(asyncio.create_subprocess_shell(self.poweroff_command))

        return web.Response(status=204)

    async def post_standby(self, request: web.Request) -> web.Response:
        """Receive a standby request from the client."""

        if self.halpi_device.firmware_version().startswith("1."):
            return web.Response(
                status=400,
                text="Standby mode is not supported in firmware version 1.x",
            )

        now = datetime.datetime.now()

        timestamp = 0

        data = await request.json()
        if "datetime" in data:
            dt = dateparser.parse(data["datetime"])
            if dt is None:
                return web.Response(status=400, text="Invalid datetime format")

            if dt < now:
                return web.Response(status=400, text="datetime must be in the future")

            timestamp = int(dt.timestamp())
        elif "delay" in data:
            try:
                delay = int(data["delay"])
            except ValueError:
                return web.Response(status=400, text="delay must be an integer")

            if delay < 0:
                return web.Response(status=400, text="delay must be positive")

            timestamp = int(now.timestamp()) + delay

        dt_str = datetime.datetime.fromtimestamp(timestamp).isoformat()

        # Use rtcwake to set the RTC alarm to wake up the system
        asyncio.create_task(
            asyncio.create_subprocess_exec("rtcwake", "-m", "no", "-t", str(timestamp))
        )

        self.halpi_device.request_standby()

        # From the OS point of view, this is a regular shutdown.
        asyncio.create_task(asyncio.create_subprocess_exec("shutdown", "-h", "now"))

        return web.Response(status=204, text=f"Set wakeup time to {dt_str}")

    async def get_config(self, request: web.Request) -> web.Response:
        """Get the configuration."""
        watchdog_timeout = self.halpi_device.watchdog_timeout()
        power_on_threshold = self.halpi_device.power_on_threshold()
        power_off_threshold = self.halpi_device.solo_power_off_threshold()
        led_brightness = self.halpi_device.led_brightness()
        auto_restart = self.halpi_device.auto_restart()
        solo_depleting_timeout = self.halpi_device.solo_depleting_timeout()

        config = {
            "watchdog_timeout": watchdog_timeout,
            "power_on_threshold": power_on_threshold,
            "solo_power_off_threshold": power_off_threshold,
            "led_brightness": led_brightness,
            "auto_restart": auto_restart,
            "solo_depleting_timeout": solo_depleting_timeout,
        }

        return web.json_response(config)

    async def get_config_key(self, request: web.Request) -> web.Response:
        """Get a configuration value."""
        key = request.match_info["key"]

        if key == "watchdog_timeout":
            value = self.halpi_device.watchdog_timeout()
        elif key == "power_on_threshold":
            value = self.halpi_device.power_on_threshold()
        elif key == "solo_power_off_threshold":
            value = self.halpi_device.solo_power_off_threshold()
        elif key == "led_brightness":
            value = self.halpi_device.led_brightness()
        elif key == "auto_restart":
            value = self.halpi_device.auto_restart()
        elif key == "solo_depleting_timeout":
            value = self.halpi_device.solo_depleting_timeout()
        else:
            return web.Response(status=404)

        return web.json_response(value)

    async def put_config_key(self, request: web.Request) -> web.Response:
        """Set a configuration value."""
        key = request.match_info["key"]

        data = await request.json()

        if key == "auto_restart":
            # Handle boolean values for auto_restart
            if isinstance(data, bool):
                self.halpi_device.set_auto_restart(data)
            elif isinstance(data, numbers.Number):
                self.halpi_device.set_auto_restart(bool(data))
            else:
                return web.Response(
                    status=400, text="Value must be a boolean or number"
                )
        elif key == "solo_depleting_timeout":
            # Handle numeric values for solo_depleting_timeout
            if isinstance(data, numbers.Number):
                self.halpi_device.set_solo_depleting_timeout(float(data))  # type: ignore
            else:
                return web.Response(status=400, text="Value must be a number")
        else:
            # check that data is a number for other config values
            if not isinstance(data, numbers.Number):
                return web.Response(status=400, text="Value must be a number")

            if key == "watchdog_timeout":
                self.halpi_device.set_watchdog_timeout(float(data))  # type: ignore
            elif key == "power_on_threshold":
                self.halpi_device.set_power_on_threshold(data)  # type: ignore
            elif key == "solo_power_off_threshold":
                self.halpi_device.set_solo_power_off_threshold(data)  # type: ignore
            elif key == "led_brightness":
                if self.halpi_device.firmware_version().startswith("1."):
                    return web.Response(
                        status=400,
                        text="LED brightness is not supported in hardware version 1.x",
                    )
                self.halpi_device.set_led_brightness(int(data))  # type: ignore
            else:
                return web.Response(status=404)

        return web.Response(status=204)

    async def get_values(self, request: web.Request) -> web.Response:
        """Get measured values and state variables."""
        dcin_voltage = self.halpi_device.dcin_voltage()
        supercap_voltage = self.halpi_device.supercap_voltage()
        input_current = self.halpi_device.input_current()
        mcu_temperature = self.halpi_device.mcu_temperature()
        pcb_temperature = self.halpi_device.pcb_temperature()

        # Include state variables as individual key-value pairs
        device_state = self.halpi_device.state()
        en5v_state = self.halpi_device.en5v_state()
        watchdog_timeout = self.halpi_device.watchdog_timeout()
        watchdog_enabled = bool(watchdog_timeout)
        watchdog_elapsed = self.halpi_device.watchdog_elapsed()

        # Include version information
        hw_version = self.halpi_device.hardware_version()
        fw_version = self.halpi_device.firmware_version()
        daemon_version = halpi.const.VERSION
        device_id = self.halpi_device.device_id()

        values = {
            "V_in": dcin_voltage,
            "V_supercap": supercap_voltage,
            "I_in": input_current,
            "T_mcu": mcu_temperature,
            "T_pcb": pcb_temperature,
            "state": device_state,
            "5v_output_enabled": en5v_state,
            "usb_port_state": self.halpi_device.usb_port_state(),
            "watchdog_enabled": watchdog_enabled,
            "watchdog_timeout": watchdog_timeout,
            "watchdog_elapsed": watchdog_elapsed,
            "hardware_version": hw_version,
            "firmware_version": fw_version,
            "daemon_version": daemon_version,
            "device_id": device_id,
        }

        return web.json_response(values)

    async def get_values_key(self, request: web.Request) -> web.Response:
        """Get a measured value or state variable."""
        key = request.match_info["key"]

        value: float | int | str

        if key == "V_in":
            value = self.halpi_device.dcin_voltage()
        elif key == "V_supercap":
            value = self.halpi_device.supercap_voltage()
        elif key == "I_in":
            value = self.halpi_device.input_current()
        elif key == "T_mcu":
            value = self.halpi_device.mcu_temperature()
        elif key == "T_pcb":
            value = self.halpi_device.pcb_temperature()
        elif key == "state":
            value = self.halpi_device.state()
        elif key == "5v_output_enabled":
            value = self.halpi_device.en5v_state()
        elif key == "usb_port_state":
            value = self.halpi_device.usb_port_state()
        elif key == "watchdog_enabled":
            value = bool(self.halpi_device.watchdog_timeout())
        elif key == "watchdog_timeout":
            value = self.halpi_device.watchdog_timeout()
        elif key == "watchdog_elapsed":
            value = self.halpi_device.watchdog_elapsed()
        elif key == "hardware_version":
            value = self.halpi_device.hardware_version()
        elif key == "firmware_version":
            value = self.halpi_device.firmware_version()
        elif key == "daemon_version":
            value = halpi.const.VERSION
        elif key == "device_id":
            value = self.halpi_device.device_id()
        else:
            return web.Response(status=404)

        return web.json_response(value)

    async def post_firmware_update(self, request: web.Request) -> web.Response:
        """Update the firmware."""
        # Get the firmware data from the request body.
        data = await request.post()
        firmware_data = data["firmware"].file  # type: ignore
        if not firmware_data:
            return web.Response(status=400, text="No firmware data provided")
        # Check if the firmware data is empty.
        if not firmware_data:
            return web.Response(status=400, text="Firmware data is empty")
        # Read the firmware data into a bytes object.
        firmware_data = firmware_data.read()

        logger.info(
            f"Starting firmware update process, size {len(firmware_data)} bytes"
        )

        result = self.halpi_device.upload_firmware_with_progress(
            firmware_data,  # The firmware data to upload
            progress_callback=lambda progress, total: logger.debug(
                f"Upload progress: {progress}/{total} "
                f"blocks ({(progress / total) * 100:.2f}%)"
            ),
        )

        if result is True:
            logger.info("Firmware upload completed successfully")
            return web.Response(status=204)
        else:
            error_message = "Firmware upload failed"
            logger.error(error_message)
            return web.Response(status=500, text=error_message)

    async def get_usb_ports(self, request: web.Request) -> web.Response:
        """Get USB port states."""
        port_state = self.halpi_device.usb_port_state()
        ports = {}
        for i in range(4):
            ports[f"usb{i}"] = bool(port_state & (1 << i))

        return web.json_response(ports)

    async def get_usb_port(self, request: web.Request) -> web.Response:
        """Get a specific USB port state."""
        port_str = request.match_info["port"]

        try:
            port = int(port_str)
            if port < 0 or port > 3:
                return web.Response(status=400, text="Port must be 0-3")

            enabled = self.halpi_device.get_usb_port(port)
            return web.json_response(enabled)

        except ValueError:
            return web.Response(status=400, text="Port must be an integer")

    async def put_usb_ports(self, request: web.Request) -> web.Response:
        """Set USB port states."""
        data = await request.json()

        if not isinstance(data, dict):
            return web.Response(status=400, text="Expected JSON object")

        # Convert individual port settings to bitfield
        current_state = self.halpi_device.usb_port_state()

        for key, value in data.items():
            if not key.startswith("usb") or len(key) != 4:
                continue

            try:
                port = int(key[3])  # Extract port number from "usb0", "usb1", etc.
                if port < 0 or port > 3:
                    continue

                if isinstance(value, bool):
                    if value:
                        current_state |= 1 << port
                    else:
                        current_state &= ~(1 << port)

            except (ValueError, IndexError):
                continue

        self.halpi_device.set_usb_port_state(current_state)
        return web.Response(status=204)

    async def put_usb_port(self, request: web.Request) -> web.Response:
        """Set a specific USB port state."""
        port_str = request.match_info["port"]

        try:
            port = int(port_str)
            if port < 0 or port > 3:
                return web.Response(status=400, text="Port must be 0-3")

            data = await request.json()
            if not isinstance(data, bool):
                return web.Response(status=400, text="Value must be a boolean")

            self.halpi_device.set_usb_port(port, data)
            return web.Response(status=204)

        except ValueError:
            return web.Response(status=400, text="Port must be an integer")


async def run_http_server(
    halpi_device: halpi.i2c.HALPIDevice,
    socket_path: pathlib.PosixPath,
    socket_group: int,
    poweroff: str,
) -> web.AppRunner:
    """Run the HTTP server."""

    handlers = RouteHandlers(halpi_device, poweroff_command=poweroff)

    app = web.Application()
    app.add_routes(
        [
            web.get("/", handlers.get_root),
            web.get("/version", handlers.get_version),
            web.post("/shutdown", handlers.post_shutdown),
            web.post("/standby", handlers.post_standby),
            web.get("/config", handlers.get_config),
            web.get("/config/{key}", handlers.get_config_key),
            web.put("/config/{key}", handlers.put_config_key),
            web.get("/values", handlers.get_values),
            web.get("/values/{key}", handlers.get_values_key),
            web.get("/usb", handlers.get_usb_ports),
            web.get("/usb/{port}", handlers.get_usb_port),
            web.put("/usb", handlers.put_usb_ports),
            web.put("/usb/{port}", handlers.put_usb_port),
            web.post("/flash", handlers.post_firmware_update),
        ]
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.UnixSite(runner, str(socket_path))
    await site.start()
    # set group ownership of the socket
    os.chown(str(socket_path), -1, socket_group)
    # set permissions of the socket
    os.chmod(str(socket_path), 0o660)  # nosec

    return runner
