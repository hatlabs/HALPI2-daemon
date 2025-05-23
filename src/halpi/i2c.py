import binascii
import struct
import time
from enum import Enum
from typing import Sequence

from loguru import logger
from smbus2 import SMBus, i2c_msg

FLASH_BLOCK_SIZE = 4096  # 4 KiB, the size of a flash block


class DFUState(Enum):
    IDLE = 0
    PREPARING = 1
    UPDATING = 2
    QUEUE_FULL = 3
    READY_TO_COMMIT = 4
    CRC_ERROR = 5
    DATA_LENGTH_ERROR = 6
    WRITE_ERROR = 7
    PROTOCOL_ERROR = 8


class States(Enum):
    BEGIN = 0
    WAIT_FOR_POWER_ON = 1
    POWER_ON_5V_OFF = 3
    POWER_ON_5V_ON = 5
    POWER_OFF_5V_ON = 7
    SHUTDOWN = 9
    WATCHDOG_REBOOT = 11
    OFF = 13
    SLEEP_SHUTDOWN = 15
    SLEEP = 17


class DeviceNotFoundError(Exception):
    pass


class HALPIDevice:
    """
    Device interface for HALPI and HALPI2 hardware.
    """

    def __init__(self, bus: int = 1, addr: int = 0x6D):
        self.bus = bus
        self.addr = addr
        self._hardware_version = "Unknown"
        self._firmware_version = "Unknown"

        # HALPI2 defaults
        self.vcap_max = 11.0
        self.dcin_max = 33.0
        self.i_max = 3.3
        self.temp_min = 273.15 - 40.0  # in Kelvin
        self.temp_max = 273.15 + 100.0  # in Kelvin

        self.hardware_version()  # force hardware version detection
        self.firmware_version()  # force firmware version detection

    @classmethod
    def factory(cls, bus: int, addr: int) -> "HALPIDevice":
        try:
            device = cls(bus, addr)
            return device
        except OSError:
            raise DeviceNotFoundError(
                "HALPI2 controller not found at I2C address %s" % addr
            )

    def i2c_query_byte(self, reg: int) -> int:
        reg_msg = i2c_msg.write(self.addr, [reg])
        read_msg = i2c_msg.read(self.addr, 1)
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, read_msg)
        b = list(read_msg)[0]  # type: ignore
        return b

    def i2c_query_bytes(self, reg: int, n: int) -> list[int]:
        reg_msg = i2c_msg.write(self.addr, [reg])
        read_msg = i2c_msg.read(self.addr, n)
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, read_msg)
        response = list(read_msg)  # type: ignore
        return response

    def i2c_query_word(self, reg: int) -> int:
        reg_msg = i2c_msg.write(self.addr, [reg])
        read_msg = i2c_msg.read(self.addr, 2)
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, read_msg)
        byte_vals = list(read_msg)  # type: ignore
        w = (byte_vals[0] << 8) | byte_vals[1]
        return w

    def i2c_write_byte(self, reg: int, val: int) -> None:
        reg_msg = i2c_msg.write(self.addr, [reg])
        write_msg = i2c_msg.write(self.addr, [val])
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, write_msg)

    def i2c_write_word(self, reg: int, val: int) -> None:
        reg_msg = i2c_msg.write(self.addr, [reg])
        # Split the word into two bytes
        buf = [(val >> 8), val & 0xFF]
        write_msg = i2c_msg.write(self.addr, buf)
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, write_msg)

    def i2c_write_bytes(self, reg: int, vals: Sequence[int]) -> None:
        reg_msg = i2c_msg.write(self.addr, [reg])
        if not all(0 <= v < 256 for v in vals):
            raise ValueError("All values must be in the range 0-255")
        write_msg = i2c_msg.write(self.addr, vals)

        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, write_msg)

    def i2c_write_read_bytes(
        self, reg: int, msg: Sequence[int], read_len: int
    ) -> list[int]:
        """
        Write a register address and message data, then read a response.
        """
        reg_msg = i2c_msg.write(self.addr, [reg])
        write_msg = i2c_msg.write(self.addr, msg)
        read_msg = i2c_msg.read(self.addr, read_len)
        with SMBus(self.bus) as bus:
            bus.i2c_rdwr(reg_msg, write_msg, read_msg)
        return list(read_msg)  # type: ignore

    def _set_hardware_version(self, version: str) -> None:
        self._hardware_version = version

    def _set_firmware_version(self, version: str) -> None:
        self._firmware_version = version
        if version.startswith("2."):
            self.read_analog = self.read_analog_word
            self.write_analog = self.write_analog_word

    def read_analog_byte(self, reg: int, scale: float) -> float:
        return scale * self.i2c_query_byte(reg) / 256

    def write_analog_byte(self, reg: int, val: float, scale: float) -> None:
        self.i2c_write_byte(reg, int(256 * val / scale))

    def read_analog_word(self, reg: int, scale: float) -> float:
        return scale * self.i2c_query_word(reg) / 65536

    def write_analog_word(self, reg: int, val: float, scale: float) -> None:
        self.i2c_write_word(reg, int(65536 * val / scale))

    def hardware_version(self) -> str:
        if self._hardware_version != "Unknown":
            return self._hardware_version

        bytes = self.i2c_query_bytes(0x03, 4)
        values = list(bytes)
        version_string = f"{values[0]}.{values[1]}.{values[2]}"
        if values[3] != 0xFF:
            version_string += f"-{values[3]}"
        self._set_hardware_version(version_string)
        return version_string

    def firmware_version(self) -> str:
        if self._firmware_version != "Unknown":
            return self._firmware_version

        bytes = list(self.i2c_query_bytes(0x04, 4))
        version_string = f"{bytes[0]}.{bytes[1]}.{bytes[2]}"
        if bytes[3] != 0xFF:
            version_string += f"-{bytes[3]}"
        self._set_firmware_version(version_string)
        return version_string

    def en5v_state(self) -> bool:
        return bool(self.i2c_query_byte(0x10))

    def watchdog_timeout(self) -> float:
        """Get the watchdog timeout in seconds. 0 means the watchdog is disabled."""
        return self.i2c_query_word(0x12) / 1000

    def set_watchdog_timeout(self, timeout: float) -> None:
        """Set the watchdog timeout in seconds. 0 disables the watchdog."""
        self.i2c_write_word(0x12, int(1000 * timeout))

    def power_on_threshold(self) -> float:
        return self.read_analog_word(0x13, self.vcap_max)

    def set_power_on_threshold(self, threshold: float) -> None:
        self.write_analog_word(0x13, threshold, self.vcap_max)

    def power_off_threshold(self) -> float:
        return self.read_analog_word(0x14, self.vcap_max)

    def set_power_off_threshold(self, threshold: float) -> None:
        self.write_analog_word(0x14, threshold, self.vcap_max)

    def state(self) -> str:
        return States(self.i2c_query_byte(0x15)).name

    def dcin_voltage(self) -> float:
        return self.read_analog_word(0x20, self.dcin_max)

    def supercap_voltage(self) -> float:
        return self.read_analog_word(0x21, self.vcap_max)

    def request_shutdown(self):
        self.i2c_write_byte(0x30, 0x01)

    def request_sleep(self):
        self.i2c_write_byte(0x31, 0x01)

    def watchdog_elapsed(self):
        return 0.1 * self.i2c_query_byte(0x16)

    def led_brightness(self) -> int:
        return self.i2c_query_byte(0x17)

    def set_led_brightness(self, brightness: int) -> None:
        self.i2c_write_byte(0x17, brightness)

    def input_current(self) -> float:
        return self.read_analog_word(0x22, self.i_max)

    def temperature(self) -> float:
        return self.read_analog_word(0x23, self.temp_max)

    def start_firmware_update(self, total_size: int) -> None:
        """
        Start a firmware update process.

        Args:
            total_size: Total size of the firmware in bytes
        """
        logger.info(f"Starting firmware update, total size: {total_size} bytes")

        # Pack the size as big-endian u32 (matching your Rust code)
        size_bytes = struct.pack(">I", total_size)

        # Write command 0x40 followed by the 4-byte size
        self.i2c_write_bytes(0x40, list(size_bytes))

    def upload_firmware_block(self, block_num: int, data: bytes) -> None:
        """
        Upload a block of firmware data.

        Args:
            block_num: Block number (0-based)
            data: Block data (up to 4096 bytes)
        """
        if len(data) > FLASH_BLOCK_SIZE:
            raise ValueError(
                f"Block size {len(data)} exceeds maximum {FLASH_BLOCK_SIZE}"
            )

        # Calculate CRC32 of the payload (block_num + block_length + data)
        block_length = len(data)
        payload = struct.pack(">HH", block_num, block_length) + data
        crc32 = binascii.crc32(payload) & 0xFFFFFFFF

        # Construct the full message: CRC32 + payload
        message = struct.pack(">I", crc32) + payload

        logger.debug(
            f"Uploading block {block_num}, size: {len(data)}, CRC32: 0x{crc32:08x}"
        )

        self.i2c_write_bytes(0x43, list(message))

    def get_dfu_status(self) -> DFUState:
        """
        Get the current DFU status.

        Returns:
            Current DFU state
        """
        status_byte = self.i2c_query_byte(0x41)

        try:
            return DFUState(status_byte)
        except ValueError:
            logger.warning(f"Unknown DFU status: {status_byte}")
            return DFUState.PROTOCOL_ERROR

    def get_blocks_written(self) -> int:
        """
        Get the number of blocks that have been written to flash.

        Returns:
            Number of blocks written
        """
        data = self.i2c_query_word(0x42)
        return data

    def commit_firmware_update(self) -> None:
        """
        Commit the firmware update.
        """
        logger.info("Committing firmware update")

        self.i2c_write_byte(0x44, 0x00)  # Any value works

    def abort_firmware_update(self) -> None:
        """
        Abort the firmware update.
        """
        logger.info("Aborting firmware update")

        self.i2c_write_byte(0x45, 0x00)  # Any value works

    def wait_for_dfu_ready(self, timeout_seconds: float = 30.0) -> bool:
        """
        Wait until the DFU system is ready to receive more data.

        Args:
            timeout_seconds: Maximum time to wait

        Returns:
            True if ready, False if timeout or error
        """
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            status = self.get_dfu_status()

            if status == DFUState.UPDATING:
                return True
            elif status == DFUState.READY_TO_COMMIT:
                return True
            elif status in [
                DFUState.CRC_ERROR,
                DFUState.PROTOCOL_ERROR,
                DFUState.WRITE_ERROR,
            ]:
                logger.error(f"DFU error state: {status}")
                return False
            elif status == DFUState.PREPARING:
                time.sleep(0.5)
                continue
            elif status == DFUState.QUEUE_FULL:
                time.sleep(0.1)
                continue
            elif status == DFUState.IDLE:
                logger.error("DFU returned to idle state unexpectedly")
                return False

            time.sleep(0.05)

        logger.error("Timeout waiting for DFU ready")
        return False

    def upload_firmware_with_progress(
        self, firmware_data: bytes, progress_callback=None
    ) -> bool:
        """
        Upload firmware with progress tracking and error handling.

        Args:
            firmware_data: Complete firmware binary
            progress_callback: Optional callback function for progress updates

        Returns:
            True if successful, False otherwise
        """
        try:
            # Start the update
            self.start_firmware_update(len(firmware_data))

            # Calculate number of blocks
            total_blocks = (
                len(firmware_data) + FLASH_BLOCK_SIZE - 1
            ) // FLASH_BLOCK_SIZE
            logger.info(f"Uploading {total_blocks} blocks")

            # Upload blocks
            for block_num in range(total_blocks):
                offset = block_num * FLASH_BLOCK_SIZE
                block_data = firmware_data[offset : offset + FLASH_BLOCK_SIZE]

                # Allow the device to respond
                time.sleep(0.1)

                # Wait for system to be ready for this block
                if not self.wait_for_dfu_ready():
                    logger.error(f"System not ready for block {block_num}")
                    self.abort_firmware_update()
                    return False

                # Upload the block
                self.upload_firmware_block(block_num, block_data)

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(block_num + 1, total_blocks)

                logger.debug(f"Uploaded block {block_num + 1}/{total_blocks}")

            # Wait for all blocks to be written
            logger.info("Waiting for all blocks to be written to flash...")
            start_time = time.time()

            while time.time() - start_time < 5.0:
                time.sleep(0.1)
                status = self.get_dfu_status()
                time.sleep(0.1)
                blocks_written = self.get_blocks_written()

                if (
                    status == DFUState.READY_TO_COMMIT
                    and blocks_written == total_blocks
                ):
                    break
                elif status in [
                    DFUState.CRC_ERROR,
                    DFUState.PROTOCOL_ERROR,
                    DFUState.WRITE_ERROR,
                ]:
                    logger.error(f"Error during flash writing: {status}")
                    time.sleep(0.1)
                    self.abort_firmware_update()
                    return False

                time.sleep(0.5)
            else:
                logger.error("Timeout waiting for flash writing to complete")
                self.abort_firmware_update()
                return False

            # Commit the update
            time.sleep(0.1)
            self.commit_firmware_update()

            logger.info("Firmware update completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Firmware update failed: {e}")
            try:
                self.abort_firmware_update()
            except OSError:
                pass  # Best effort cleanup
            return False
