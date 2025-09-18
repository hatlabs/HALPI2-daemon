import asyncio
import pathlib
from typing import Any, Dict

import aiohttp
import typer
from rich.console import Console
from rich.table import Table

import halpi.const

"""HALPI2 command line interface communicates with the halpid daemon and
allows the user to observe and control the device."""

app = typer.Typer(
    name="halpi",
    help=__doc__,
    add_completion=False,
)
console = Console()

# dictionary of state variables
state: Dict[str, Any] = {}


async def get_json(session: aiohttp.ClientSession, url: str) -> Any:
    """Get JSON data from the given URL."""
    async with session.get(url) as resp:
        return await resp.json()


async def post_json(
    session: aiohttp.ClientSession, url: str, data: Dict[Any, Any]
) -> int:
    """Post JSON data to the given URL."""
    async with session.post(url, json=data) as resp:
        return resp.status


async def put_json(session: aiohttp.ClientSession, url: str, data: Any) -> int:
    """Put JSON data to the given URL."""
    async with session.put(url, json=data) as resp:
        return resp.status


async def async_print_status(socket_path: pathlib.Path) -> None:
    """Print status and measurement data from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        values = await get_json(session, "http://localhost:8080/values")

        # Print all gathered data in a neat table

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Value", justify="right")
        table.add_column("Unit")

        table.add_row("hardware_version", str(values["hardware_version"]), "")
        table.add_row("firmware_version", str(values["firmware_version"]), "")
        table.add_section()

        table.add_row("state", str(values["state"]), "")
        table.add_row("5v_output_enabled", str(values["5v_output_enabled"]), "")

        # Show USB port states in a compact format
        usb_state = values["usb_port_state"]
        usb_summary = []
        for i in range(4):
            if usb_state & (1 << i):
                usb_summary.append(f"USB{i}:✓")
            else:
                usb_summary.append(f"USB{i}:✗")
        table.add_row("usb_ports", " ".join(usb_summary), "")

        table.add_row("watchdog_enabled", str(values["watchdog_enabled"]), "")
        if values["watchdog_enabled"]:
            table.add_row("watchdog_timeout", f"{values['watchdog_timeout']:.1f}", "s")
            table.add_row("watchdog_elapsed", f"{values['watchdog_elapsed']:.1f}", "s")
        table.add_section()

        table.add_row("V_in", f"{values['V_in']:.1f}", "V")
        if values["I_in"] is not None:
            table.add_row("I_in", f"{values['I_in']:.2f}", "A")
        table.add_row("V_supercap", f"{values['V_supercap']:.2f}", "V")
        if values["T_mcu"] is not None:
            table.add_row("T_mcu", f"{values['T_mcu'] - 273.15:.1f}", "°C")
        if values["T_pcb"] is not None:
            table.add_row("T_pcb", f"{values['T_pcb'] - 273.15:.1f}", "°C")

        console.print(table)


@app.command("status")
def status() -> None:
    """Print status and measurement data from the device."""
    asyncio.run(async_print_status(state["socket"]))


async def async_shutdown(socket_path: pathlib.Path) -> None:
    """Tell the device to wait for shutdown."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await post_json(session, "http://localhost:8080/shutdown", {})
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


@app.command("shutdown")
def shutdown(
    standby: bool = typer.Option(
        False, "--standby", help="Enter standby mode instead of shutdown"
    ),
    time: str | None = typer.Option(
        None,
        help="Wakeup time for standby mode (absolute datetime or delay in seconds)",
    ),
) -> None:
    """Tell the device to shutdown or enter standby mode."""
    if standby:
        if time is None:
            console.print("Error: --time is required when using --standby", style="red")
            raise typer.Exit(code=1)

        time_dict = {}
        # test if time is an integer
        try:
            int(time)
            time_dict = {"delay": time}
        except ValueError:
            # assume time is an absolute time
            time_dict = {"datetime": time}

        asyncio.run(async_standby(state["socket"], time_dict))
    else:
        asyncio.run(async_shutdown(state["socket"]))


async def async_standby(socket_path: pathlib.Path, time: Dict[str, str]) -> None:
    """Tell the device to enter standby mode."""

    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await post_json(session, "http://localhost:8080/standby", time)
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


async def async_flash_firmware(
    socket_path: pathlib.Path, firmware: pathlib.Path
) -> None:
    """Flash firmware to the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        with open(firmware, "rb") as f:
            url = "http://localhost:8080/flash"
            data = aiohttp.FormData()
            filename = firmware.name
            data.add_field("firmware", f, filename=filename)
            response = await session.post(url, data=data)
            if response.status != 204:
                error_text = await response.text()
                console.print(
                    (
                        "Error: Firmware flashing failed with HTTP "
                        f"status {response.status}"
                    ),
                    style="red",
                )
                if error_text:
                    console.print(f"Error details: {error_text}", style="red")
                raise typer.Exit(code=1)


@app.command("flash")
def flash_firmware(
    firmware_file: pathlib.Path = typer.Argument(
        ...,
        help="Path to the firmware file to flash.",
    ),
) -> None:
    """
    Flash firmware to the device.
    """
    try:
        asyncio.run(async_flash_firmware(state["socket"], firmware_file))
        console.print("Firmware flashing completed successfully", style="green")
    except typer.Exit:
        # Re-raise typer.Exit to preserve the exit code
        raise
    except Exception as e:
        console.print(f"Error: Firmware flashing failed: {e}", style="red")
        raise typer.Exit(code=1)


async def async_firmware_version(socket_path: pathlib.Path) -> None:
    """Get the firmware version from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await get_json(session, "http://localhost:8080/version")
        if "firmware_version" in response:
            console.print(f"Firmware version: {response['firmware_version']}")
        else:
            console.print("Error: Firmware version not found", style="red")
            raise typer.Exit(code=1)


@app.command("version")
def version() -> None:
    """Get the CLI version."""
    console.print(halpi.const.VERSION)


async def async_get_config(socket_path: pathlib.Path) -> dict[str, Any]:
    """Get all configuration from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_json(session, "http://localhost:8080/config")
        assert isinstance(result, dict), "Expected a dictionary response"
        return result


async def async_get_config_key(socket_path: pathlib.Path, key: str) -> Any:
    """Get a specific configuration key from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_json(session, f"http://localhost:8080/config/{key}")
        assert isinstance(result, dict), "Expected a dictionary response"
        return result


async def async_get_values(socket_path: pathlib.Path) -> dict[str, Any]:
    """Get all values from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_json(session, "http://localhost:8080/values")
        assert isinstance(result, dict), "Expected a dictionary response"
        return result


async def async_get_value_key(socket_path: pathlib.Path, key: str) -> Any:
    """Get a specific value key from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        return await get_json(session, f"http://localhost:8080/values/{key}")


@app.command("get")
def get(
    measurement: str = typer.Argument(
        ...,
        help=(
            "Measurement to retrieve (e.g., V_in, V_supercap, I_in, "
            "T_mcu, state, 5v_output_enabled, usb_port_state, watchdog_enabled, "
            "watchdog_timeout, watchdog_elapsed, hardware_version, firmware_version, "
            "device_id)"
        ),
    ),
) -> None:
    """Get individual measurements and runtime values."""
    try:
        value = asyncio.run(async_get_value_key(state["socket"], measurement))
        console.print(value)
    except Exception as e:
        console.print(f"Error getting measurement '{measurement}': {e}", style="red")
        raise typer.Exit(code=1)


async def async_set_config_key(socket_path: pathlib.Path, key: str, value: Any) -> None:
    """Set a specific configuration key on the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await put_json(session, f"http://localhost:8080/config/{key}", value)
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


@app.command("config")
def config(
    action: str | None = typer.Argument(
        None,
        help=(
            "Action: 'get' to retrieve a key, "
            "'set' to set a key, or leave empty to show all"
        ),
    ),
    key: str | None = typer.Argument(None, help="Configuration key to get or set"),
    value: str | None = typer.Argument(
        None, help="Value to set (only used with 'set' action)"
    ),
) -> None:
    """Get all configuration, get a specific config key, or set a config key value."""
    if action is None:
        # Show all config
        config_data = asyncio.run(async_get_config(state["socket"]))

        table = Table(show_header=True, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Value", justify="right")

        for config_key, config_value in config_data.items():
            if isinstance(config_value, float):
                formatted_value = f"{config_value:.2f}".rstrip("0")
                if formatted_value.endswith("."):
                    formatted_value += "0"
            else:
                formatted_value = str(config_value)
            table.add_row(config_key, formatted_value)

        console.print(table)
    elif action == "get":
        if key is None:
            console.print("Error: key is required when using 'get' action", style="red")
            raise typer.Exit(code=1)
        # Get specific key
        try:
            key_value = asyncio.run(async_get_config_key(state["socket"], key))
            console.print(key_value)
        except Exception as e:
            console.print(f"Error getting config key '{key}': {e}", style="red")
            raise typer.Exit(code=1)
    elif action == "set":
        if key is None or value is None:
            console.print(
                "Error: both key and value are required when using 'set' action",
                style="red",
            )
            raise typer.Exit(code=1)
        # Set specific key
        try:
            # Try to convert value to appropriate type
            # First try int, then float, fallback to string
            numeric_value: float | int | str | None = None
            try:
                numeric_value = int(value)
            except ValueError:
                try:
                    numeric_value = float(value)
                except ValueError:
                    # Check for boolean strings
                    if value.lower() in ("true", "false"):
                        numeric_value = value.lower() == "true"
                    else:
                        numeric_value = value

            asyncio.run(async_set_config_key(state["socket"], key, numeric_value))
            console.print(f"Set {key} to {value}")
        except Exception as e:
            console.print(f"Error setting config key '{key}': {e}", style="red")
            raise typer.Exit(code=1)
    else:
        console.print(
            f"Error: unknown action '{action}'. Use 'get' or 'set'", style="red"
        )
        raise typer.Exit(code=1)


async def async_get_usb_ports(socket_path: pathlib.Path) -> dict[str, bool]:
    """Get all USB port states from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_json(session, "http://localhost:8080/usb")
        assert isinstance(result, dict), "Expected a dictionary response"
        return result


async def async_get_usb_port(socket_path: pathlib.Path, port: int) -> bool:
    """Get a specific USB port state from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await get_json(session, f"http://localhost:8080/usb/{port}")
        assert isinstance(result, bool), "Expected a boolean response"
        return result


async def async_set_usb_ports(
    socket_path: pathlib.Path, ports: dict[str, bool]
) -> None:
    """Set USB port states on the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await put_json(session, "http://localhost:8080/usb", ports)
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


async def async_set_usb_port(
    socket_path: pathlib.Path, port: int, enabled: bool
) -> None:
    """Set a specific USB port state on the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await put_json(session, f"http://localhost:8080/usb/{port}", enabled)
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


@app.command("usb")
def usb(
    action: str | None = typer.Argument(
        None,
        help=(
            "Action: 'get' to show port states, "
            "'enable' or 'disable' to control ports, or leave empty to show all ports"
        ),
    ),
    target: str | None = typer.Argument(
        None,
        help="Port number (0-3) or 'all' for all ports (required for enable/disable)",
    ),
) -> None:
    """Control USB port power states.

    Examples:
      halpi usb                  # Show all port states
      halpi usb get              # Show all port states
      halpi usb enable 0         # Enable USB port 0
      halpi usb disable all      # Disable all USB ports
      halpi usb enable all       # Enable all USB ports
    """
    try:
        if action is None or action == "get":
            # Show USB port states
            ports = asyncio.run(async_get_usb_ports(state["socket"]))

            table = Table(show_header=True, box=None)
            table.add_column("Port", style="bold")
            table.add_column("Enabled", justify="right")

            for port_name, enabled in ports.items():
                status = "✓" if enabled else "✗"
                style = "green" if enabled else "red"
                table.add_row(port_name.upper(), status, style=style)

            console.print(table)

        elif action == "enable":
            if target is None:
                console.print("Error: Specify port number (0-3) or 'all'", style="red")
                raise typer.Exit(code=1)

            if target == "all":
                # Enable all ports
                ports_data = {"usb0": True, "usb1": True, "usb2": True, "usb3": True}
                asyncio.run(async_set_usb_ports(state["socket"], ports_data))
                console.print("All USB ports enabled")
            else:
                # Enable specific port
                try:
                    port = int(target)
                    if port < 0 or port > 3:
                        console.print("Error: Port must be 0-3", style="red")
                        raise typer.Exit(code=1)
                    asyncio.run(async_set_usb_port(state["socket"], port, True))
                    console.print(f"USB port {port} enabled")
                except ValueError:
                    console.print(
                        "Error: Target must be port number (0-3) or 'all'", style="red"
                    )
                    raise typer.Exit(code=1)

        elif action == "disable":
            if target is None:
                console.print("Error: Specify port number (0-3) or 'all'", style="red")
                raise typer.Exit(code=1)

            if target == "all":
                # Disable all ports
                ports_data = {
                    "usb0": False,
                    "usb1": False,
                    "usb2": False,
                    "usb3": False,
                }
                asyncio.run(async_set_usb_ports(state["socket"], ports_data))
                console.print("All USB ports disabled")
            else:
                # Disable specific port
                try:
                    port = int(target)
                    if port < 0 or port > 3:
                        console.print("Error: Port must be 0-3", style="red")
                        raise typer.Exit(code=1)
                    asyncio.run(async_set_usb_port(state["socket"], port, False))
                    console.print(f"USB port {port} disabled")
                except ValueError:
                    console.print(
                        "Error: Target must be port number (0-3) or 'all'", style="red"
                    )
                    raise typer.Exit(code=1)
        else:
            console.print(
                f"Error: unknown action '{action}'. Use 'get', 'enable', or 'disable'",
                style="red",
            )
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"Error controlling USB ports: {e}", style="red")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    socket: pathlib.Path = typer.Option(
        pathlib.Path("/var/run/halpid.sock"), "--socket", "-s"
    ),
) -> None:
    """HALPI command line interface communicates with the halpid daemon and
    allows the user to observe and control the device."""
    state["socket"] = socket

    # If no command was provided, show help
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


def main():
    app()


if __name__ == "__main__":
    main()
