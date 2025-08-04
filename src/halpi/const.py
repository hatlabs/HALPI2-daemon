# Config file for HALPI daemon
CONFIG_FILE_LOCATION = "/etc/halpid/halpid.conf"

# Default I2C bus for Raspberry Pi
I2C_BUS = 1

# Default I2C address for HALPI
I2C_ADDR = 0x6D

# After this many seconds of blackout, the daemon will shut down the Pi
DEFAULT_BLACKOUT_TIME_LIMIT = 5.0

# This is the input voltage limit that counts as a blackout
DEFAULT_BLACKOUT_VOLTAGE_LIMIT = 9.0

# Daemon version
VERSION = "4.0.0"
