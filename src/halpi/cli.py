import asyncio
import pathlib
from typing import Any, Dict

import aiohttp
import typer
from rich.console import Console
from rich.table import Table

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


async def async_print_all(socket_path: pathlib.Path) -> None:
    """Print all data from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        coro1 = get_json(session, "http://localhost:8080/version")
        coro2 = get_json(session, "http://localhost:8080/state")
        coro3 = get_json(session, "http://localhost:8080/config")
        coro4 = get_json(session, "http://localhost:8080/values")
        version, state, config, values = await asyncio.gather(
            coro1, coro2, coro3, coro4
        )

        # Print all gathered data in a neat table

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Value", justify="right")
        table.add_column("Unit")

        table.add_row("Hardware version", str(version["hardware_version"]), "")
        table.add_row("Firmware version", str(version["firmware_version"]), "")
        table.add_row("Daemon version", str(version["daemon_version"]), "")
        table.add_section()

        table.add_row("State", str(state["state"]), "")
        table.add_row("5V output", str(state["5v_output_enabled"]), "")
        table.add_row("Watchdog enabled", str(state["watchdog_enabled"]), "")
        table.add_section()

        table.add_row("Watchdog timeout", f"{config['watchdog_timeout']:.1f}", "s")
        table.add_row("Power-on threshold", f"{config['power_on_threshold']:.1f}", "V")
        table.add_row(
            "Power-off threshold", f"{config['power_off_threshold']:.1f}", "V"
        )
        if config["led_brightness"] is not None:
            table.add_row(
                "LED brightness", f"{100 * config['led_brightness'] / 255:.1f}", "%"
            )
        table.add_section()

        table.add_row("Voltage in", f"{values['V_in']:.1f}", "V")
        if values["I_in"] is not None:
            table.add_row("Current in", f"{values['I_in']:.2f}", "A")
        table.add_row("Supercap voltage", f"{values['V_supercap']:.2f}", "V")
        if values["T_mcu"] is not None:
            table.add_row("MCU temperature", f"{values['T_mcu'] - 273.15:.1f}", "°C")

        console.print(table)


@app.command("print")
def print_all() -> None:
    """Print all data from the device."""
    asyncio.run(async_print_all(state["socket"]))


async def async_shutdown(socket_path: pathlib.Path) -> None:
    """Tell the device to wait for shutdown."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await post_json(session, "http://localhost:8080/shutdown", {})
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


@app.command("shutdown")
def shutdown(
    standby: bool = typer.Option(False, "--standby", help="Enter standby mode instead of shutdown"),
    time: str = typer.Option(None, help="Wakeup time for standby mode (absolute datetime or delay in seconds)")
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
                console.print(
                    f"Error: Received HTTP status {response.status}", style="red"
                )


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
    asyncio.run(async_flash_firmware(state["socket"], firmware_file))


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


@app.command("firmware-version")
def firmware_version() -> None:
    """Get the firmware version from the device."""
    asyncio.run(async_firmware_version(state["socket"]))


async def async_get_config(socket_path: pathlib.Path) -> Dict[str, Any]:
    """Get all configuration from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        return await get_json(session, "http://localhost:8080/config")


async def async_get_config_key(socket_path: pathlib.Path, key: str) -> Any:
    """Get a specific configuration key from the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        return await get_json(session, f"http://localhost:8080/config/{key}")


async def async_set_config_key(socket_path: pathlib.Path, key: str, value: Any) -> None:
    """Set a specific configuration key on the device."""
    connector = aiohttp.UnixConnector(path=str(socket_path))
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await put_json(session, f"http://localhost:8080/config/{key}", value)
        if response != 204:
            console.print(f"Error: Received HTTP status {response}", style="red")


@app.command("config")
def config(
    action: str = typer.Argument(None, help="Action: 'get' to retrieve a key, 'set' to set a key, or leave empty to show all"),
    key: str = typer.Argument(None, help="Configuration key to get or set"),
    value: str = typer.Argument(None, help="Value to set (only used with 'set' action)")
) -> None:
    """Get all configuration, get a specific config key, or set a config key value."""
    if action is None:
        # Show all config
        config_data = asyncio.run(async_get_config(state["socket"]))

        table = Table(show_header=True, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Value", justify="right")

        for config_key, config_value in config_data.items():
            table.add_row(config_key, str(config_value))

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
            console.print("Error: both key and value are required when using 'set' action", style="red")
            raise typer.Exit(code=1)
        # Set specific key
        try:
            # Try to convert value to appropriate type
            # First try int, then float, fallback to string
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
        console.print(f"Error: unknown action '{action}'. Use 'get' or 'set'", style="red")
        raise typer.Exit(code=1)
@app.callback()
def callback(
    socket: pathlib.Path = typer.Option(
        pathlib.Path("/var/run/halpid.sock"), "--socket", "-s"
    ),
) -> None:
    """HALPI command line interface communicates with the halpid daemon and
    allows the user to observe and control the device."""
    state["socket"] = socket


def main():
    app()


if __name__ == "__main__":
    main()
