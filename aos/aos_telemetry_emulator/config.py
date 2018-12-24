import os

# All parameters are here for development needs

# emulator data update time
EMULATOR_UPDATE_TIME = 0.4

# Listen address
CONTROL_API_ADDRESS = ("0.0.0.0", 80)

# Vehicle VIN and driver UUID
DRIVER_UUID = os.environ.get("DRIVER_UUID", "NoDriverUUID")
VEHICLE_VIN = os.environ.get("VEHICLE_VIN")
