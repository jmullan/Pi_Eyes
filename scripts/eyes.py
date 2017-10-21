#!/usr/bin/python

from __future__ import print_function

# This is a hasty port of the Teensy eyes code to Python...all kludgey with
# an embarrassing number of globals in the frame() function and stuff.
# Needed to get SOMETHING working, can focus on improvements next.

import time

import pi3d

from adafruit.pieyes import face, graphics, raspberry, renderers


def main():
    """Run two eyes."""
    # INPUT CONFIG for eye motion
    # ANALOG INPUTS REQUIRE SNAKE EYES BONNET

    JOYSTICK_X_FLIP = False  # If True, reverse stick X axis
    JOYSTICK_Y_FLIP = False  # If True, reverse stick Y axis
    PUPIL_IN_FLIP = False  # If True, reverse reading from PUPIL_IN
    TRACKING = True  # If True, eyelid tracks pupil
    PUPIL_SMOOTH = 16  # If > 0, filter input from PUPIL_IN
    AUTOBLINK = True  # If True, eyes blink autonomously

    BLINK_PIN = -1
    WINK_L_PIN = -1
    WINK_R_PIN = -1
    gpio = False
    if gpio:
        BLINK_PIN = 23    # GPIO pin for blink button (BOTH eyes)
        WINK_L_PIN = 22    # GPIO pin for LEFT eye wink button
        WINK_R_PIN = 24 # GPIO pin for RIGHT eye wink button

    PUPIL_PIN = -1
    JOYSTICK_X_PIN = -1
    JOYSTICK_Y_PIN = -1

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
        blink_pin=BLINK_PIN,
        wink_l_pin=WINK_L_PIN,
        wink_r_pin=WINK_R_PIN,
        joystick_x_pin=JOYSTICK_X_PIN,
        joystick_y_pin=JOYSTICK_Y_PIN,
        pupil_pin=PUPIL_PIN
    )

    keyboard_handler = face.KeyboardHandler()

    blink_triggers = [rpi.get_blink_state, keyboard_handler.spacebar]

    blinker = face.Blinker(blink_triggers, AUTOBLINK)
    left_winker = face.Winker(blinker, rpi.get_wink_l_state)
    right_winker = face.Winker(blinker, rpi.get_wink_r_state)
    if rpi.pupil_pin >= 0:
        dilator = face.AnalogDilator(PUPIL_SMOOTH, PUPIL_IN_FLIP, rpi)
    else:
        dilator = face.FractalDilator()
    if rpi.joystick_x_pin >= 0 and rpi.joystick_y_pin >= 0:
        looker = face.AnalogLooker(JOYSTICK_X_FLIP, JOYSTICK_Y_FLIP, rpi)
    else:
        looker = face.AutonomousLooker()
    eye_graphics = graphics.EyeGraphics("graphics/eye.svg", texture_data)

    two_eyes = face.TwoEyes(
        display,
        eye_graphics,
        TRACKING,
        left_winker,
        right_winker,
        dilator,
        looker
    )

    # MAIN LOOP -- runs continuously
    while True:
        try:
            keyboard_handler.read()
        except KeyboardInterrupt:
            keyboard_handler.close()
            two_eyes.stop()
            exit(0)

        try:
            two_eyes.frame()
        except Exception as e:
            print('Exception %r' % e)
            time.sleep(10)


if __name__ == '__main__':
    main()
