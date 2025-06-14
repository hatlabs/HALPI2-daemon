import asyncio
import time
from subprocess import check_call

from loguru import logger

from halpi.i2c import HALPIDevice


async def run_state_machine(
    halpi_device: HALPIDevice,
    blackout_time_limit: float,
    blackout_voltage_limit: float,
    dry_run: bool = False,
    poweroff: str = "/sbin/poweroff",
) -> None:
    state = "START"
    blackout_time = 0.0
    dcin_voltage = 0.0

    while True:
        # TODO: Provide facilities for reporting the states and voltages
        # en5v_state = dev.en5v_state()
        # dev_state = dev.state()
        try:
            # Read the DC input voltage from the HALPI device
            dcin_voltage = halpi_device.dcin_voltage()
        except Exception as e:
            logger.error(f"Failed to read DC input voltage: {e}")

        if state == "START":
            halpi_device.set_watchdog_timeout(10)
            state = "OK"
        elif state == "OK":
            if dcin_voltage < blackout_voltage_limit:
                logger.warning("Detected blackout")
                blackout_time = time.time()
                state = "BLACKOUT"
        elif state == "BLACKOUT":
            if dcin_voltage > blackout_voltage_limit:
                logger.info("Power resumed")
                state = "OK"
            elif time.time() - blackout_time > blackout_time_limit:
                # didn't get power back in time
                logger.warning(
                    f"Blacked out for {blackout_time_limit} s, shutting down"
                )
                state = "SHUTDOWN"
        elif state == "SHUTDOWN":
            if dry_run:
                logger.warning(f"Would execute {poweroff}")
            else:
                # inform the hat about this sad state of affairs
                halpi_device.request_shutdown()
                logger.info(f"Executing {poweroff}")
                check_call(["sudo", poweroff])
            state = "DEAD"
        elif state == "DEAD":
            # just wait for the inevitable
            pass
        await asyncio.sleep(1.0)
