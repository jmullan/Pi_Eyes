#!/usr/bin/python

from __future__ import print_function

# This is a PARED-DOWN version of eyes.py designed for the Gakken
# WorldEye display.  It renders a single eye (centered on screen) and
# does NOT require the OLED or TFT displays...doesn't even require the
# Snake Eyes Bonnet if you just have it running in autonomous mode.
# Code is just as in-progress as eyes.py and could use some work.

import time

import pi3d

from adafruit.pieyes import face, graphics, raspberry, renderers


def main():
    """Run a single eye."""
    # INPUT CONFIG for eye motion
    # ANALOG INPUTS REQUIRE SNAKE EYES BONNET
    JOYSTICK_X_FLIP = False # If True, reverse stick X axis
    JOYSTICK_Y_FLIP = False # If True, reverse stick Y axis
    PUPIL_IN_FLIP   = False # If True, reverse reading from PUPIL_IN
    TRACKING        = True  # If True, eyelid tracks pupil
    PUPIL_SMOOTH    = 16    # If > 0, filter input from PUPIL_IN
    AUTOBLINK       = True  # If True, eye blinks autonomously

    # Set up display and initialize pi3d

    display = pi3d.Display.create(samples=4)
    display.set_background(0, 0, 0, 1)  # r,g,b,alpha

    # A 2D camera is used, mostly to allow for pixel-accurate eye placement,
    # but also because perspective isn't really helpful or needed here, and
    # also this allows eyelids to be handled somewhat easily as 2D planes.
    # Line of sight is down Z axis, allowing conventional X/Y cartesion
    # coords for 2D positions.
    pi3d.Camera(is_3d=False, at=(0, 0, 0), eye=(0, 0, -1000))
    pi3d.Light(lightpos=(0, -500, -500), lightamb=(0.2, 0.2, 0.2))

    # Load SVG file, extract paths & convert to point lists
    texture_data = {
        'iris': ('graphics/iris.jpg', False),
        'sclera': ('graphics/sclera.png', True),
        'lid': ('graphics/lid.png', True)
    }

    rpi = raspberry.Pi(
        blink_pin=-1,
        wink_l_pin=-1,
        wink_r_pin=-1,
        joystick_x_pin=-1,
        joystick_y_pin=-1,
        pupil_pin=-1
    )
    keyboard_handler = face.KeyboardHandler()
    blink_triggers = [rpi.get_blink_state, keyboard_handler.spacebar]
    blinker = face.Blinker(blink_triggers, AUTOBLINK)
    winker = face.Winker(blinker, rpi.get_wink_l_state)
    if rpi.pupil_pin >= 0:
        dilator = face.AnalogDilator(PUPIL_SMOOTH, PUPIL_IN_FLIP, rpi)
    else:
        dilator = face.FractalDilator()
    if rpi.joystick_x_pin >= 0 and rpi.joystick_y_pin >= 0:
        looker = face.AnalogLooker(JOYSTICK_X_FLIP, JOYSTICK_Y_FLIP, rpi)
    else:
        looker = face.AutonomousLooker()
    eye_graphics = graphics.EyeGraphics(
        "graphics/cyclops-eye.svg",
        texture_data
    )

    cyclops = face.Cyclops(
        display,
        eye_graphics,
        TRACKING,
        winker,
        dilator,
        looker
    )

    # MAIN LOOP -- runs continuously
    while True:
        try:
            keyboard_handler.read()
        except KeyboardInterrupt:
            keyboard_handler.close()
            cyclops.stop()
            exit(0)

        try:
            cyclops.frame()
        except Exception as e:
            print('Exception %r' % e)
            time.sleep(10)


if __name__ == '__main__':
    main()
