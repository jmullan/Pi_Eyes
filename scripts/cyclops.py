#!/usr/bin/python

# This is a PARED-DOWN version of eyes.py designed for the Gakken
# WorldEye display.  It renders a single eye (centered on screen) and
# does NOT require the OLED or TFT displays...doesn't even require the
# Snake Eyes Bonnet if you just have it running in autonomous mode.
# Code is just as in-progress as eyes.py and could use some work.

import math
import random
import time
from xml.dom.minidom import parse

import pi3d
from svg.path import Path, parse_path

from gfxutil import *
from pieyes import common, face, raspberry

JOYSTICK_X_FLIP = False # If True, reverse stick X axis
JOYSTICK_Y_FLIP = False # If True, reverse stick Y axis
PUPIL_IN_FLIP   = False # If True, reverse reading from PUPIL_IN
TRACKING        = True  # If True, eyelid tracks pupil
PUPIL_SMOOTH    = 16    # If > 0, filter input from PUPIL_IN
AUTOBLINK       = True  # If True, eye blinks autonomously


# Load SVG file, extract paths & convert to point lists --------------------

# Thanks Glen Akins for the symmetrical-lidded cyclops eye SVG!
# Iris & pupil have been scaled down slightly in this version to compensate
# for how the WorldEye distorts things...looks OK on WorldEye now but might
# seem small and silly if used with the regular OLED/TFT code.
dom               = parse("graphics/cyclops-eye.svg")
vb                = getViewBox(dom)
pupilMinPts       = getPoints(dom, "pupilMin"      , 32, True , True )
pupilMaxPts       = getPoints(dom, "pupilMax"      , 32, True , True )
irisPts           = getPoints(dom, "iris"          , 32, True , True )
scleraFrontPts    = getPoints(dom, "scleraFront"   ,  0, False, False)
scleraBackPts     = getPoints(dom, "scleraBack"    ,  0, False, False)
upperLidClosedPts = getPoints(dom, "upperLidClosed", 33, False, True )
upperLidOpenPts   = getPoints(dom, "upperLidOpen"  , 33, False, True )
upperLidEdgePts   = getPoints(dom, "upperLidEdge"  , 33, False, False)
lowerLidClosedPts = getPoints(dom, "lowerLidClosed", 33, False, False)
lowerLidOpenPts   = getPoints(dom, "lowerLidOpen"  , 33, False, False)
lowerLidEdgePts   = getPoints(dom, "lowerLidEdge"  , 33, False, False)


# Set up display and initialize pi3d ---------------------------------------

DISPLAY = pi3d.Display.create(samples=4)
DISPLAY.set_background(0, 0, 0, 1) # r,g,b,alpha

# eyeRadius is the size, in pixels, at which the whole eye will be rendered.
if DISPLAY.width <= (DISPLAY.height * 2):
    # For WorldEye, eye size is -almost- full screen height
    eyeRadius   = DISPLAY.height / 2.1
else:
    eyeRadius   = DISPLAY.height * 2 / 5

# A 2D camera is used, mostly to allow for pixel-accurate eye placement,
# but also because perspective isn't really helpful or needed here, and
# also this allows eyelids to be handled somewhat easily as 2D planes.
# Line of sight is down Z axis, allowing conventional X/Y cartesion
# coords for 2D positions.
cam    = pi3d.Camera(is_3d=False, at=(0,0,0), eye=(0,0,-1000))
shader = pi3d.Shader("uv_light")
light  = pi3d.Light(lightpos=(0, -500, -500), lightamb=(0.2, 0.2, 0.2))


# Load texture maps --------------------------------------------------------

irisMap   = pi3d.Texture("graphics/iris.jpg"  , mipmap=False,
              filter=pi3d.GL_LINEAR)
scleraMap = pi3d.Texture("graphics/sclera.png", mipmap=False,
              filter=pi3d.GL_LINEAR, blend=True)
lidMap    = pi3d.Texture("graphics/lid.png"   , mipmap=False,
              filter=pi3d.GL_LINEAR, blend=True)
# U/V map may be useful for debugging texture placement; not normally used
#uvMap     = pi3d.Texture("graphics/uv.png"    , mipmap=False,
#              filter=pi3d.GL_LINEAR, blend=False, m_repeat=True)


# Initialize static geometry -----------------------------------------------

# Transform point lists to eye dimensions
scalePoints(pupilMinPts      , vb, eyeRadius)
scalePoints(pupilMaxPts      , vb, eyeRadius)
scalePoints(irisPts          , vb, eyeRadius)
scalePoints(scleraFrontPts   , vb, eyeRadius)
scalePoints(scleraBackPts    , vb, eyeRadius)
scalePoints(upperLidClosedPts, vb, eyeRadius)
scalePoints(upperLidOpenPts  , vb, eyeRadius)
scalePoints(upperLidEdgePts  , vb, eyeRadius)
scalePoints(lowerLidClosedPts, vb, eyeRadius)
scalePoints(lowerLidOpenPts  , vb, eyeRadius)
scalePoints(lowerLidEdgePts  , vb, eyeRadius)

# Regenerating flexible object geometry (such as eyelids during blinks, or
# iris during pupil dilation) is CPU intensive, can noticably slow things
# down, especially on single-core boards.  To reduce this load somewhat,
# determine a size change threshold below which regeneration will not occur;
# roughly equal to 1/2 pixel, since 2x2 area sampling is used.

# Determine change in pupil size to trigger iris geometry regen
irisRegenThreshold = 0.0
a = pointsBounds(pupilMinPts) # Bounds of pupil at min size (in pixels)
b = pointsBounds(pupilMaxPts) # " at max size
maxDist = max(abs(a[0] - b[0]), abs(a[1] - b[1]), # Determine distance of max
              abs(a[2] - b[2]), abs(a[3] - b[3])) # variance around each edge
# maxDist is motion range in pixels as pupil scales between 0.0 and 1.0.
# 1.0 / maxDist is one pixel's worth of scale range.  Need 1/2 that...
if maxDist > 0:
    irisRegenThreshold = 0.5 / maxDist

# Determine change in eyelid values needed to trigger geometry regen.
# This is done a little differently than the pupils...instead of bounds,
# the distance between the middle points of the open and closed eyelid
# paths is evaluated, then similar 1/2 pixel threshold is determined.
upperLidRegenThreshold = 0.0
lowerLidRegenThreshold = 0.0
p1 = upperLidOpenPts[len(upperLidOpenPts) / 2]
p2 = upperLidClosedPts[len(upperLidClosedPts) / 2]
dx = p2[0] - p1[0]
dy = p2[1] - p1[1]
d  = dx * dx + dy * dy
if d > 0: upperLidRegenThreshold = 0.5 / math.sqrt(d)
p1 = lowerLidOpenPts[len(lowerLidOpenPts) / 2]
p2 = lowerLidClosedPts[len(lowerLidClosedPts) / 2]
dx = p2[0] - p1[0]
dy = p2[1] - p1[1]
d  = dx * dx + dy * dy
if d > 0: lowerLidRegenThreshold = 0.5 / math.sqrt(d)

# Generate initial iris mesh; vertex elements will get replaced on
# a per-frame basis in the main loop, this just sets up textures, etc.
iris = meshInit(32, 4, True, 0, 0.5/irisMap.iy, False)
iris.set_textures([irisMap])
iris.set_shader(shader)
irisZ = zangle(irisPts, eyeRadius)[0] * 0.99 # Get iris Z depth, for later

# Eyelid meshes are likewise temporary; texture coordinates are
# assigned here but geometry is dynamically regenerated in main loop.
upperEyelid = meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
upperEyelid.set_textures([lidMap])
upperEyelid.set_shader(shader)
lowerEyelid = meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
lowerEyelid.set_textures([lidMap])
lowerEyelid.set_shader(shader)

# Generate sclera for eye...start with a 2D shape for lathing...
angle1 = zangle(scleraFrontPts, eyeRadius)[1] # Sclera front angle
angle2 = zangle(scleraBackPts , eyeRadius)[1] # " back angle
aRange = 180 - angle1 - angle2
pts    = []
for i in range(24):
        ca, sa = pi3d.Utility.from_polar((90 - angle1) - aRange * i / 23)
        pts.append((ca * eyeRadius, sa * eyeRadius))

eye = pi3d.Lathe(path=pts, sides=64)
eye.set_textures([scleraMap])
eye.set_shader(shader)
reAxis(eye, 0.0)


# Init global stuff --------------------------------------------------------

mykeys = pi3d.Keyboard() # For capturing key presses

frames = 0
beginningTime = time.time()

eye.positionX(0.0)
iris.positionX(0.0)
upperEyelid.positionX(0.0)
upperEyelid.positionZ(-eyeRadius - 42)
lowerEyelid.positionX(0.0)
lowerEyelid.positionZ(-eyeRadius - 42)

prevPupilScale = -1.0 # Force regen on first frame
prevUpperLidWeight = 0.5
prevLowerLidWeight = 0.5
prevUpperLidPts = pointsInterp(upperLidOpenPts, upperLidClosedPts, 0.5)
prevLowerLidPts = pointsInterp(lowerLidOpenPts, lowerLidClosedPts, 0.5)

ruRegen = True
rlRegen = True

trackingPos = 0.3


class Cyclops(face.Face):
    def __init__(self, middle_eye, dilator):
        super(Cyclops, self).__init__()
        self.middle_eye = middle_eye
        self.dilator = dilator

    def frame():
        # Generate one frame of imagery
        global frames
        global iris
        global pupilMinPts, pupilMaxPts, irisPts, irisZ
        global eye
        global upperEyelid, lowerEyelid
        global upperLidOpenPts, upperLidClosedPts, lowerLidOpenPts, lowerLidClosedPts
        global upperLidEdgePts, lowerLidEdgePts
        global prevUpperLidPts, prevLowerLidPts
        global prevUpperLidWeight, prevLowerLidWeight
        global prevPupilScale
        global irisRegenThreshold, upperLidRegenThreshold, lowerLidRegenThreshold
        global luRegen, llRegen, ruRegen, rlRegen
        global trackingPos

        DISPLAY.loop_running()

        now = time.time()

        frames += 1
        # if(now > beginningTime):
        #     print(frames/(now-beginningTime))

        curX, curY = self.looker.getXY(now)
        # change 0.0 - 1.0 to -30 - 30
        curX = (curX * 60) - 30
        curY = (curY * 60) - 30

        p = self.dilator.get_dilation()
        # Regenerate iris geometry only if size changed by >= 1/2 pixel
        if abs(p - prevPupilScale) >= irisRegenThreshold:
            # Interpolate points between min and max pupil sizes
            interPupil = pointsInterp(pupilMinPts, pupilMaxPts, p)
            # Generate mesh between interpolated pupil and iris bounds
            mesh = pointsMesh(None, interPupil, irisPts, 4, -irisZ, True)
            iris.re_init(pts=mesh)
            prevPupilScale = p

        if TRACKING:
            # 0 = fully up, 1 = fully down
            n = 0.5 - curY / 70.0
            if n < 0.0:
                n = 0.0
            elif n > 1.0:
                n = 1.0
            trackingPos = (trackingPos * 3.0 + n) * 0.25

        blink_state = self.middle_eye.get_open_amount(now)
        newUpperLidWeight = trackingPos + (blink_state * (1.0 - trackingPos))
        newLowerLidWeight = (1.0 - trackingPos) + (blink_state * trackingPos)

        if (ruRegen or (abs(newUpperLidWeight - prevUpperLidWeight) >= upperLidRegenThreshold)):
            newUpperLidPts = pointsInterp(
                upperLidOpenPts, upperLidClosedPts, newUpperLidWeight)
            if newUpperLidWeight > prevUpperLidWeight:
                upperEyelid.re_init(pts=pointsMesh(
                    upperLidEdgePts, prevUpperLidPts,
                    newUpperLidPts, 5, 0, False, True))
            else:
                upperEyelid.re_init(pts=pointsMesh(
                    upperLidEdgePts, newUpperLidPts,
                    prevUpperLidPts, 5, 0, False, True))
            prevUpperLidWeight = newUpperLidWeight
            prevUpperLidPts = newUpperLidPts
            ruRegen = True
        else:
            ruRegen = False

        if (rlRegen or (abs(newLowerLidWeight - prevLowerLidWeight) >= lowerLidRegenThreshold)):
            newLowerLidPts = pointsInterp(lowerLidOpenPts, lowerLidClosedPts, newLowerLidWeight)
                if newLowerLidWeight > prevLowerLidWeight:
                    lowerEyelid.re_init(
                        pts=pointsMesh(
                            lowerLidEdgePts, prevLowerLidPts,
                            newLowerLidPts, 5, 0, False, True
                        )
                    )
                else:
                    lowerEyelid.re_init(
                        pts=pointsMesh(
                            lowerLidEdgePts, newLowerLidPts,
                            prevLowerLidPts, 5, 0, False, True
                        )
                    )
                prevLowerLidWeight = newLowerLidWeight
                prevLowerLidPts = newLowerLidPts
                rlRegen = True
        else:
                rlRegen = False

        # Draw eye

        iris.rotateToX(curY)
        iris.rotateToY(curX)
        iris.draw()
        eye.rotateToX(curY)
        eye.rotateToY(curX)
        eye.draw()
        upperEyelid.draw()
        lowerEyelid.draw()

        k = mykeys.read()
        if k == 27:
            mykeys.close()
            DISPLAY.stop()
            exit(0)


def main():
    """Run a single eye."""
    rpi = raspberry.Pi()
    blinker = face.Blinker(rpi.get_blink_state, True)
    eye = face.Winker(blinker, rpi.get_wink_l_state)
    if rpi.pupil_pin >= 0:
        dilator = face.AnalogDilator(pi, PUPIL_IN_FLIP, PUPIL_SMOOTH)
    else:
        dilator = face.FractalDilator()

    if rpi.joystick_x_pin >= 0 and rpi.joystick_y_pin >= 0:
        looker = face.AnalogLooker(JOYSTICK_FLIP_X, JOYSTICK_FLIP_Y, rpi)
    else:
        looker = face.AutonomousLooker()
    cyclops = Cyclops(eye, dilator, looker)

    # MAIN LOOP -- runs continuously
    while True:
        cyclops.frame()


if __name__ == '__main__':
    main()
