import random
import time

from pieyes import common

DEBLINK = 0
ENBLINK = 1


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

    def __init__(self, blink_trigger, autoblink):
        self.blink_target = DEBLINK
        self.blink_trigger = blink_trigger
        self.autoblink = autoblink
        self.time_of_stop_blink = 0.0
        self.time_of_next_blink = 1.0
        self.closed = False

    def close(self):
        """Force the blinker closed."""
        self.closed = True

    def frame(self, dilation):
        """Generate one frame of imagery."""
        raise NotImplementedError

    def should_autoblink(self, now):
        """Has it been long enough since the prior autoblink?"""
        return self.autoblink and now >= self.time_of_next_blink

    def get_blink_target(self, now):
        """Determine if the eye should be opening or closing."""

        duration = random.uniform(
            self.BLINK_MIN_LENGTH_MS,
            self.BLINK_MAX_LENGTH_MS
        ) / 1000.0

        blink_interval = random.uniform(
            self.BLINK_MIN_INTERVAL_MS,
            self.BLINK_MAX_INTERVAL_MS
        ) / 1000.0

        if self.closed or self.blink_target == DEBLINK:
            if self.closed or self.blink_trigger() or self.should_autoblink(now):
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
            percent_time = (self.duration - elapsed) / self.duration
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
    pass
