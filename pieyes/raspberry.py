import thread

import Adafruit_ADS1x15

from pieyes import common


class Pi(object):
    """Raspberry Pi Things."""

    BLINK_PIN = 23    # GPIO pin for blink button
    GPIO = None

    def __init__(
            self,
            blink_pin=-1,
            wink_l_pin=-1,
            wink_r_pin=-1,
            joystick_x_pin=-1,
            joystick_y_pin=-1,
            pupil_pin=-1
    ):
        self.adc_values = [0] * 4

        self.blink_pin = blink_pin
        self.wink_l_pin = wink_l_pin
        self.wink_r_pin = wink_r_pin

        self.joystick_x_pin = joystick_x_pin
        self.joystick_y_pin = joystick_y_pin
        self.pupil_pin = pupil_pin

        if any(
                x > -1
                for x in [
                    self.blink_pin,
                    self.wink_l_pin,
                    self.wink_r_pin,
                    self.joystick_x_pin,
                    self.joystick_y_pin,
                    self.pupil_pin
                ]
        ):
            self.init_gpio()

    def init_gpio(self):
        """GPIO initialization"""
        from RPi import GPIO
        self.GPIO = GPIO

        self.GPIO.setmode(self.GPIO.BCM)

        pins = [
            self.blink_pin,
            self.wink_l_pin,
            self.wink_r_pin
        ]

        for pin in pins:
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def _check_pin(self, pin):
        """Check if a pin is set and is low."""
        return pin >= 0 and self.GPIO.input(pin) == self.GPIO.LOW

    def init_adc(self):
        """Set up adc sampling if needed.

        https://learn.adafruit.com/animated-snake-eyes-bonnet-for-raspberry-pi/customizing-the-hardware
        """
        if (
                self.joystick_x_pin >= 0 or
                self.joystick_y_pin >= 0 or
                self.pupil_pin >= 0
        ):
            adc = Adafruit_ADS1x15.ADS1015()
        else:
            adc = None

        # Start ADC sampling thread if needed:
        if adc:
            thread.start_new_thread(
                common.adc_thread, (adc, self.adc_values))

    def get_blink_state(self):
        """Check the blink pin for the current blink state."""
        return self._check_pin(self.blink_pin)

    def get_wink_l_state(self):
        """Check the left wink pin for the current wink state."""
        return self._check_pin(self.wink_l_pin)

    def get_wink_r_state(self):
        """Check the right wink pin for the current wink state."""
        return self._check_pin(self.wink_r_pin)

    def get_joystick_x(self):
        """Check the joystick x pin for position."""
        return self.adc_values[self.joystick_x_pin]

    def get_joystick_y(self):
        """Check the joystick y pin for position."""
        return self.adc_values[self.joystick_y_pin]

    def get_dilation(self):
        """Check the pupil pin for the current dilation."""
        return self.adc_values[self.pupil_pin]
