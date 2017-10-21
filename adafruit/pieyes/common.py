"""Common functions."""
import random
import time

PUPIL_MIN = 0.0   # Lower analog range from PUPIL_IN
PUPIL_MAX = 1.0   # Upper analog range from PUPIL_IN


def adc_thread(adc, dest):
    """Read all adc values into dest.

    Because ADC reads are blocking operations, they normally would slow down
    the animation loop noticably, especially when reading multiple channels
    (even when using high data rate settings).  To avoid this, ADC channels
    are read in a separate thread and stored in the global list adc_value[],
    which the animation loop can read at its leisure (with immediate results,
    no slowdown).  Since there's a finite limit to the animation frame rate,
    we intentionally use a slower data rate (rather than sleep()) to lessen
    the impact of this thread.  data_rate of 250 w/4 ADC channels provides
    at most 75 Hz update from the ADC, which is plenty for this task.
    """
    while True:
        for i in dest.keys():
            # ADC input range is +- 4.096V
            # ADC output is -2048 to +2047
            # Analog inputs will be 0 to ~3.3V,
            # thus 0 to 1649-ish.  Read & clip:
            value = adc.read_adc(i, gain=1, data_rate=250)
            if value < 0:
                value = 0
            elif value > 1649:
                value = 1649
            dest[i] = value / 1649.0  # Store as 0.0 to 1.0
        time.sleep(0)  # allow the context to switch if needed


def split(start_value, end_value, duration, lid_range, face):
    """Recursive simulated pupil response when no analog sensor.

    @param start_value Pupil scale starting value (0.0 to 1.0)
    @param end_value   Pupil scale ending value (0.0 to 1.0)
    @param duration   Start-to-end time, floating-point seconds
    @param lid_range  +/- random pupil scale at midpoint
    """
    start_time = time.time()
    if lid_range >= 0.125:  # Limit subdvision count, because recursion
        duration *= 0.5  # Split time & lid_range in half for subdivision,
        lid_range *= 0.5  # then pick random center point within lid_range:
        mid_value = (
            (start_value + end_value - lid_range) *
            0.5 +
            random.uniform(0.0, lid_range)
        )
        split(start_value, mid_value, duration, lid_range, face)
        split(mid_value, end_value, duration, lid_range, face)
    else:
        # No more subdivisons, do iris motion...
        delta_value = end_value - start_value
        while True:
            delta_time = time.time() - start_time
            if delta_time >= duration:
                break
            new_value = start_value + delta_value * delta_time / duration
            if new_value < PUPIL_MIN:
                new_value = PUPIL_MIN
            elif new_value > PUPIL_MAX:
                new_value = PUPIL_MAX
            face.frame(new_value)  # Draw frame w/interim pupil scale value


def parse_analog_input(current_pupil_scale, value, flip_in, smooth_level):
    """Turn an analog input into a dilation value."""
    # Pupil scale from sensor
    if flip_in:
        value = 1.0 - value
    # If you need to calibrate PUPIL_MIN and MAX,
    # add a 'print v' here for testing.
    if value < PUPIL_MIN:
        value = PUPIL_MIN
    elif value > PUPIL_MAX:
        value = PUPIL_MAX
    # Scale to 0.0 to 1.0:
    dilation = (value - PUPIL_MIN) / (PUPIL_MAX - PUPIL_MIN)
    if smooth_level > 0:
        dilation = (
            (current_pupil_scale * (smooth_level - 1) + dilation) /
            smooth_level
        )
    return dilation
