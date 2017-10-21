import random
import time

import pi3d

from adafruit.pieyes import common, renderers

DEBLINK = 0
ENBLINK = 1


class KeyboardHandler(object):
    def __init__(self):
        self.keyboard = pi3d.Keyboard()
        self.keys = {
            32: False
        }

    def close(self):
        self.keyboard.close()

    def read(self):
        key = self.keyboard.read()
        if key == 27:
            raise KeyboardInterrupt()
        if key in self.keys:
            self.keys[key] = True

    def spacebar(self):
        space = self.keys[32]
        self.keys[32] = False


class Winker(object):
    """Determines how much an eye is closed.

    Based on the blink target (all open or all closed) and
    the amount of time it takes to blink open or closed.
    """
    MIN_CLOSING_TIME_MS = 70
    MAX_CLOSING_TIME_MS = 215
    MIN_OPENING_TIME_MS = 100
    MAX_OPENING_TIME_MS = 200

    def __init__(self, blinker, wink_trigger):
        self.blinker = blinker
        self.wink_trigger = wink_trigger
        self.blink_target = -1
        self.start_action = 0
        self.duration = 0
        self.finish_action = 0

    def get_open_amount(self, now):
        """How far open should this eye be."""

        blink_target = self.blinker.get_blink_target(now)
        wink_target = self.wink_trigger()

        target = blink_target or wink_target

        if target != self.blink_target:
            self.start_action = now
            self.blink_target = target
            if target == ENBLINK:
                self.duration = random.uniform(
                    self.MIN_CLOSING_TIME_MS,
                    self.MAX_CLOSING_TIME_MS
                ) / 1000
            else:
                self.duration = random.uniform(
                    self.MIN_OPENING_TIME_MS,
                    self.MAX_OPENING_TIME_MS
                ) / 1000
            self.finish_action = self.duration + now

        remaining = self.finish_action - now
        if self.duration and remaining > 0:
            if target == DEBLINK:
                return remaining / self.duration
            else:
                elapsed = now - self.start_action
                return elapsed / self.duration
        else:
            if target == DEBLINK:
                return 0.0
            else:
                return 1.0


class Blinker(object):
    """Triggers autonomous blinking

    Timings from:
    http://rsif.royalsocietypublishing.org/content/10/85/20130227
    """

    # how long it takes to close + how long it stays closed
    BLINK_MIN_LENGTH_MS = Winker.MIN_CLOSING_TIME_MS + 54
    BLINK_MAX_LENGTH_MS = Winker.MAX_CLOSING_TIME_MS + 62
    # how long it takes to open
    BLINK_MIN_INTERVAL_MS = 2000
    BLINK_MAX_INTERVAL_MS = 10000

    def __init__(self, blink_triggers, autoblink):
        self.blink_target = DEBLINK
        self.blink_triggers = blink_triggers or []
        if autoblink:
            self.blink_triggers.append(self._should_autoblink)
        self.time_of_stop_blink = 0.0
        self.time_of_next_blink = 1.0
        self.closed = False
        self._now = time.time()

    def _should_autoblink(self):
        """Has it been long enough since the prior autoblink?

        This internal method expects self._now to be set.
        """
        return self._now >= self.time_of_next_blink
        
    def should_autoblink(self, now):
        """Has it been long enough since the prior autoblink?"""
        self._now = time.time()
        return self._should_autoblink()

    def get_blink_target(self, now):
        """Determine if the eye should be opening or closing."""
        self._now = now
        duration = random.uniform(
            self.BLINK_MIN_LENGTH_MS,
            self.BLINK_MAX_LENGTH_MS
        ) / 1000.0

        blink_interval = random.uniform(
            self.BLINK_MIN_INTERVAL_MS,
            self.BLINK_MAX_INTERVAL_MS
        ) / 1000.0

        if any(x() for x in self.blink_triggers):
            self.blink_target = ENBLINK
            self.time_of_stop_blink = now + duration
            self.time_of_next_blink = now + blink_interval
            self.closed = False
        elif now > self.time_of_stop_blink:
            self.blink_target = DEBLINK
        return self.blink_target


class Dilator(object):
    """Handles dilation."""
    PUPIL_MIN = 0.0
    PUPIL_MAX = 1.0

    def __init__(self):
        self.current_dilation = 1.0

    def get_dilation(self):
        """Get the current dilation."""
        raise NotImplementedError


class AnalogDilator(Dilator):
    def __init__(self, smooth, flip_in, rpi):
        super(AnalogDilator, self).__init__()
        self.smooth = smooth
        self.flip_in = flip_in
        self.rpi = rpi

    def get_dilation(self):
        self.current_dilation = common.parse_analog_input(
            self.current_dilation,
            self.rpi.get_dilation(),
            self.flip_in,
            self.smooth
        )
        return self.current_dilation


class FractalDilator(Dilator):
    """Self-similar divisions of time."""
    def __init__(self):
        super(FractalDilator, self).__init__()
        self.start_value = 0.0
        now = time.time()
        self.start_time = now
        self.duration = 4.0
        self.steps = 8
        self.step_time = self.duration / self.steps
        target = random.random()
        self.targets = self.fill_values(self.start_value, target, self.steps)

    def get_dilation(self):
        now = time.time()
        elapsed = now - self.start_time
        if elapsed >= self.duration:
            # We are done, so schedule new steps
            self.current_dilation = self.targets[-1]
            self.start_value = self.current_dilation
            target = random.random()
            self.targets = self.fill_values(
                self.start_value, target, self.steps)
            self.start_time = now
        else:
            # Determine what step we are in and how far into we are
            percent_time = elapsed / self.duration
            step = int(self.steps * percent_time)
            step_elapsed = elapsed - (step * self.step_time)
            step_percent = step_elapsed / self.step_time
            if step == 0:
                prior_step = self.start_value
            else:
                prior_step = self.targets[step - 1]
            delta = self.targets[step] - prior_step
            self.current_dilation = prior_step + (delta * step_percent)
        return self.current_dilation

    def clamp(self, dilation):
        """Keep the dilation in an acceptable range."""
        return max(min(dilation, self.PUPIL_MAX), self.PUPIL_MIN)

    def fill_values(self, start_value, end_value, list_size, variance=1.0):
        """Divide up the duration into steps with individual variance."""
        if list_size == 1:
            return [end_value]
        else:
            vari = variance / 2
            list_size = list_size / 2
            mid_value = (start_value + end_value) / 2
            fudged = self.clamp(mid_value + random.uniform(-variance, vari))
            return (
                self.fill_values(start_value, fudged, list_size, vari) +
                self.fill_values(fudged, end_value, list_size, vari)
            )


class Looker(object):
    def get_x_y(self, now):
        raise NotImplementedError


class AnalogLooker(Looker):
    def __init__(self, flip_x, flip_y, rpi):
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.rpi = rpi

    def get_x_y(self, _):
        current_x = self.rpi.get_joystick_x()
        if self.flip_x:
            current_x = 1.0 - current_x

        current_y = self.rpi.get_joystick_y()
        if self.flip_y:
            current_y = 1.0 - current_y

        return current_x, current_y


class AutonomousLooker(Looker):
    def __init__(self):
        self.is_moving = False
        self.start_time = time.time()
        self.start_x = 0.5
        self.start_y = 0.5
        self.dest_x = 0.5
        self.dest_y = 0.5
        self.cur_x = 0.5
        self.cur_y = 0.5
        self.hold_duration = random.uniform(0.1, 1.1)
        self.move_duration = random.uniform(0.075, 0.5)

    def get_x_y(self, now):
        # Autonomous eye position
        dt = now - self.start_time
        if self.is_moving:
            if dt <= self.move_duration:
                scale = (now - self.start_time) / self.move_duration
                # Ease in/out curve: 3*t^2-2*t^3
                scale = 3.0 * scale * scale - 2.0 * scale * scale * scale
                self.cur_x = self.start_x + (
                    self.dest_x - self.start_x) * scale
                self.cur_y = self.start_y + (
                    self.dest_y - self.start_y) * scale
            else:
                self.start_x = self.dest_x
                self.start_y = self.dest_y
                self.cur_x = self.dest_x
                self.cur_y = self.dest_y
                self.hold_duration = random.uniform(0.1, 1.1)
                self.start_time = now
                self.is_moving = False
        elif dt >= self.hold_duration:
            self.dest_x = random.uniform(0.0, 1.0)
            # n = math.sqrt(1.0 - self.dest_x * self.dest_x)
            # self.dest_y = random.uniform(-n, n)
            self.dest_y = random.uniform(0.0, 1.0)
            self.move_duration = random.uniform(0.075, 0.175)
            self.start_time = now
            self.is_moving = True
        return self.cur_x, self.cur_y


class Face(object):
    """The base class for displaying faces."""
    def __init__(self, display, eye_graphics, tracking):
        self.frames = 0
        self.display = display
        self.eye_graphics = eye_graphics
        self.eye_graphics.set_eye_radius(self.get_eye_radius())
        self.tracking = tracking
        self.cam = None
        self.light = None

    def stop(self):
        if self.display:
            self.display.stop()

    def get_eye_radius(self):
        """Get the pixel size for the whole eye on the screen.

        eye_radius is the size, in pixels, at which the whole eye will be
        rendered onscreen.
        """
        raise NotImplementedError

    def get_eye_position(self):
        """Get the left or right pixel offset for the eye on the screen.

        eyePosition, in pixels, is the offset (left or right) from the
        center point of the screen to the center of each eye.  This geometry
        is explained more in-depth in fbx2.c.
        """
        raise NotImplementedError

    def frame(self):
        """Generate one frame of imagery."""
        raise NotImplementedError


class TwoEyes(Face):
    def __init__(
            self,
            display,
            graphics,
            tracking,
            left_winker,
            right_winker,
            dilator,
            looker
    ):
        super(TwoEyes, self).__init__(display, graphics, tracking)

        self.left_winker = left_winker
        self.right_winker = right_winker
        self.dilator = dilator
        self.looker = looker

        eye_radius = self.get_eye_radius()
        eye_position = self.get_eye_position()
        convergence = 2.0

        self.left_sclera = renderers.ScleraRenderer(graphics, eye_radius, eye_position, False, convergence)
        self.right_sclera = renderers.ScleraRenderer(graphics, eye_radius, eye_position, True, convergence)

        self.left_iris = renderers.IrisRenderer(graphics, eye_radius, eye_position, False, convergence)
        self.right_iris = renderers.IrisRenderer(graphics, eye_radius, eye_position, True, convergence)

        self.left_upper_lid = renderers.UpperLidRenderer(graphics, eye_radius, eye_position, False)
        self.right_upper_lid = renderers.UpperLidRenderer(graphics, eye_radius, eye_position, True)
        self.left_lower_lid = renderers.LowerLidRenderer(graphics, eye_radius, eye_position, False)
        self.right_lower_lid = renderers.LowerLidRenderer(graphics, eye_radius, eye_position, True)

    def frame(self):
        # Generate one frame of imagery

        self.display.loop_running()

        now = time.time()

        self.frames += 1

        curX, curY = self.looker.get_x_y(now)

        p = self.dilator.get_dilation()
        self.left_iris.set_dilation(p)
        self.right_iris.set_dilation(p)

        tracking_pos = 0.3
        if self.tracking:
            n = 0.4 - curY
            tracking_pos = (tracking_pos * 3.0 + n) * 0.25

        left_blink_state = self.left_winker.get_open_amount(now) * 0.75 + 0.25
        self.left_upper_lid.update(left_blink_state, tracking_pos)
        self.left_lower_lid.update(left_blink_state, tracking_pos)

        right_blink_state = self.right_winker.get_open_amount(
            now) * 0.75 + 0.25
        self.right_upper_lid.update(right_blink_state, tracking_pos)
        self.right_lower_lid.update(right_blink_state, tracking_pos)

        # change 0.0 - 1.0 to -30 - 30
        curX = (curX * 60) - 30
        curY = (curY * 60) - 30

        # Right eye (on screen left)

        self.right_iris.rotate_to(curX, curY)
        self.right_iris.draw()
        self.right_sclera.rotate_to(curX, curY)
        self.right_sclera.draw()

        # Left eye (on screen right)

        self.left_iris.rotate_to(curX, curY)
        self.left_iris.draw()
        self.left_sclera.rotate_to(curX, curY)
        self.left_sclera.draw()

        self.left_upper_lid.draw()
        self.left_lower_lid.draw()
        self.right_upper_lid.draw()
        self.right_lower_lid.draw()

    def get_eye_radius(self):

        # eye_radius is the size, in pixels, at which the whole eye will be
        # rendered onscreen
        if self.display.width <= (self.display.height * 2):
            eye_radius = self.display.width / 5
        else:
            eye_radius = self.display.height * 2 / 5
        return eye_radius

    def get_eye_position(self):

        # eye_position, also pixels, is the offset (left or right) from
        # the center point of the screen to the center of each eye.  This
        # geometry is explained more in-depth in fbx2.c.
        if self.display.width <= (self.display.height * 2):
            eye_position = self.display.width / 4
        else:
            eye_position = self.display.height / 2
        return eye_position


class Cyclops(Face):
    def __init__(
            self,
            display,
            graphics,
            tracking,
            winker,
            dilator,
            looker
    ):
        super(Cyclops, self).__init__(display, graphics, tracking)
        self.winker = winker
        self.dilator = dilator
        self.looker = looker

        eye_radius = self.get_eye_radius()
        eye_position = self.get_eye_position()

        self.sclera = renderers.ScleraRenderer(graphics, eye_radius, eye_position, False, 0)

        self.iris = renderers.IrisRenderer(graphics, eye_radius, eye_position, False, 0)

        self.upper_lid = renderers.UpperLidRenderer(graphics, eye_radius, eye_position, False)
        self.lower_lid = renderers.LowerLidRenderer(graphics, eye_radius, eye_position, False)

    def frame(self):
        # Generate one frame of imagery

        self.display.loop_running()

        now = time.time()

        self.frames += 1

        curX, curY = self.looker.get_x_y(now)

        p = self.dilator.get_dilation()
        self.iris.set_dilation(p)

        tracking_pos = 0.3
        if self.tracking:
            n = 0.4 - curY
            tracking_pos = (tracking_pos * 3.0 + n) * 0.25

        blink_state = self.winker.get_open_amount(now) * 0.75 + 0.25
        self.upper_lid.update(blink_state, tracking_pos)
        self.lower_lid.update(blink_state, tracking_pos)

        # change 0.0 - 1.0 to -30 - 30
        curX = (curX * 60) - 30
        curY = (curY * 60) - 30

        self.iris.rotate_to(curX, curY)
        self.iris.draw()
        self.sclera.rotate_to(curX, curY)
        self.sclera.draw()

        self.upper_lid.draw()
        self.lower_lid.draw()

    def get_eye_radius(self):

        # eye_radius is the size, in pixels, at which the whole eye will be
        # rendered onscreen
        if self.display.width <= (self.display.height * 2):
            eye_radius = self.display.width / 2.1
        else:
            eye_radius = self.display.height * 2 / 5
        return eye_radius

    def get_eye_position(self):
        # eye_position, also pixels, is the offset (left or right) from
        # the center point of the screen to the center of each eye.  This
        # geometry is explained more in-depth in fbx2.c.
        return 0
