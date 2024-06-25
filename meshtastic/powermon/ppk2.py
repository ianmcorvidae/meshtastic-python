"""Classes for logging power consumption of meshtastic devices."""

import logging
import threading
import time
from typing import Optional

from ppk2_api import ppk2_api  # type: ignore[import-untyped]

from .power_supply import PowerError, PowerSupply


class PPK2PowerSupply(PowerSupply):
    """Interface for talking with the NRF PPK2 high-resolution micro-power supply.
    Power Profiler Kit II is what you should google to find it for purchase.
    """

    def __init__(self, portName: Optional[str] = None):
        """Initialize the PowerSupply object.

        portName (str, optional): The port name of the power supply. Defaults to "/dev/ttyACM0".
        """
        if not portName:
            devs = ppk2_api.PPK2_API.list_devices()
            if not devs or len(devs) == 0:
                raise PowerError("No PPK2 devices found")
            elif len(devs) > 1:
                raise PowerError(
                    "Multiple PPK2 devices found, please specify the portName"
                )
            else:
                portName = devs[0]

        self.r = r = ppk2_api.PPK2_MP(portName)  # serial port will be different for you
        r.get_modifiers()

        self.r.start_measuring()  # send command to ppk2
        self.current_measurements = [0.0]  # reset current measurements to 0mA
        self.measuring = True

        self.measurement_thread = threading.Thread(
            target=self.measurement_loop, daemon=True, name="ppk2 measurement"
        )
        self.measurement_thread.start()

        logging.info("Connected to Power Profiler Kit II (PPK2)")

        super().__init__()  # we call this late so that the port is already open and _getRawWattHour callback works

    def measurement_loop(self):
        """Endless measurement loop will run in a thread."""
        while self.measuring:
            read_data = self.r.get_data()
            if read_data != b"":
                samples, _ = self.r.get_samples(read_data)
                self.current_measurements += samples
            time.sleep(0.001)  # FIXME figure out correct sleep duration

    def get_min_current_mA(self):
        """Returns max current in mA (since last call to this method)."""
        return min(self.current_measurements) / 1000

    def get_max_current_mA(self):
        """Returns max current in mA (since last call to this method)."""
        return max(self.current_measurements) / 1000

    def get_average_current_mA(self):
        """Returns average current in mA (since last call to this method)."""
        average_current_mA = (
            sum(self.current_measurements) / len(self.current_measurements)
        ) / 1000  # measurements are in microamperes, divide by 1000

        return average_current_mA

    def reset_measurements(self):
        """Reset current measurements."""
        # Use the last reading as the new only reading (to ensure we always have a valid current reading)
        self.current_measurements = [ self.current_measurements[-1] ]

    def close(self) -> None:
        """Close the power meter."""
        self.measuring = False
        self.r.stop_measuring()  # send command to ppk2
        self.measurement_thread.join()  # wait for our thread to finish
        super().close()

    def setIsSupply(self, s: bool):
        """If in supply mode we will provide power ourself, otherwise we are just an amp meter."""

        self.r.set_source_voltage(
            int(self.v * 1000)
        )  # set source voltage in mV BEFORE setting source mode
        # Note: source voltage must be set even if we are using the amp meter mode

        if (
            not s
        ):  # min power outpuf of PPK2.  If less than this assume we want just meter mode.
            self.r.use_ampere_meter()
        else:
            self.r.use_source_meter()  # set source meter mode

    def powerOn(self):
        """Power on the supply."""
        self.r.toggle_DUT_power("ON")

    def powerOff(self):
        """Power off the supply."""
        self.r.toggle_DUT_power("OFF")
