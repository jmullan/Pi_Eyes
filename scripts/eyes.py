#!/usr/bin/python

# This is a hasty port of the Teensy eyes code to Python...all kludgey with
# an embarrassing number of globals in the frame() function and stuff.
# Needed to get SOMETHING working, can focus on improvements next.

import time
from xml.dom.minidom import parse

import pi3d

from pieyes import face, gfxutil, raspberry, renderers

# INPUT CONFIG for eye motion ----------------------------------------------
# ANALOG INPUTS REQUIRE SNAKE EYES BONNET

JOYSTICK_X_IN = -1  # Analog input for eye horiz pos (-1 = auto)
JOYSTICK_Y_IN = -1  # Analog input for eye vert position (")
PUPIL_IN = -1  # Analog input for pupil control (-1 = auto)
JOYSTICK_X_FLIP = False  # If True, reverse stick X axis
JOYSTICK_Y_FLIP = False  # If True, reverse stick Y axis
PUPIL_IN_FLIP = False  # If True, reverse reading from PUPIL_IN
TRACKING = True  # If True, eyelid tracks pupil
PUPIL_SMOOTH = 16  # If > 0, filter input from PUPIL_IN
PUPIL_MIN = 0.0  # Lower analog range from PUPIL_IN
PUPIL_MAX = 1.0  # Upper "
WINK_L_PIN = 22  # GPIO pin for LEFT eye wink button
BLINK_PIN = 23  # GPIO pin for blink button (BOTH eyes)
WINK_R_PIN = 24  # GPIO pin for RIGHT eye wink button
AUTOBLINK = True  # If True, eyes blink autonomously


# Load SVG file, extract paths & convert to point lists --------------------

dom = parse("graphics/eye.svg")
vb = gfxutil.getViewBox(dom)
pupilMinPts = gfxutil.getPoints(dom, "pupilMin", 32, True, True)
pupilMaxPts = gfxutil.getPoints(dom, "pupilMax", 32, True, True)
irisPts = gfxutil.getPoints(dom, "iris", 32, True, True)
scleraFrontPts = gfxutil.getPoints(dom, "scleraFront", 0, False, False)
scleraBackPts = gfxutil.getPoints(dom, "scleraBack", 0, False, False)
upperLidClosedPts = gfxutil.getPoints(dom, "upperLidClosed", 33, False, True)
upperLidOpenPts = gfxutil.getPoints(dom, "upperLidOpen", 33, False, True)
upperLidEdgePts = gfxutil.getPoints(dom, "upperLidEdge", 33, False, False)
lowerLidClosedPts = gfxutil.getPoints(dom, "lowerLidClosed", 33, False, False)
lowerLidOpenPts = gfxutil.getPoints(dom, "lowerLidOpen", 33, False, False)
lowerLidEdgePts = gfxutil.getPoints(dom, "lowerLidEdge", 33, False, False)


# Set up display and initialize pi3d ---------------------------------------

DISPLAY = pi3d.Display.create(samples=4)
DISPLAY.set_background(0, 0, 0, 1)  # r,g,b,alpha

# eyeRadius is the size, in pixels, at which the whole eye will be rendered
# onscreen.  eyePosition, also pixels, is the offset (left or right) from
# the center point of the screen to the center of each eye.  This geometry
# is explained more in-depth in fbx2.c.
if DISPLAY.width <= (DISPLAY.height * 2):
    eyeRadius = DISPLAY.width / 5
    eyePosition = DISPLAY.width / 4
else:
    eyeRadius = DISPLAY.height * 2 / 5
    eyePosition = DISPLAY.height / 2

# A 2D camera is used, mostly to allow for pixel-accurate eye placement,
# but also because perspective isn't really helpful or needed here, and
# also this allows eyelids to be handled somewhat easily as 2D planes.
# Line of sight is down Z axis, allowing conventional X/Y cartesion
# coords for 2D positions.
cam = pi3d.Camera(is_3d=False, at=(0, 0, 0), eye=(0, 0, -1000))
shader = pi3d.Shader("uv_light")
light = pi3d.Light(lightpos=(0, -500, -500), lightamb=(0.2, 0.2, 0.2))


# Load texture maps --------------------------------------------------------

iris_map = pi3d.Texture(
    "graphics/iris.jpg",
    mipmap=False,
    filter=pi3d.GL_LINEAR
)
scleraMap = pi3d.Texture(
    "graphics/sclera.png",
    mipmap=False,
    filter=pi3d.GL_LINEAR,
    blend=True
)
lidMap = pi3d.Texture(
    "graphics/lid.png",
    mipmap=False,
    filter=pi3d.GL_LINEAR,
    blend=True
)
# U/V map may be useful for debugging texture placement; not normally used
# uvMap     = pi3d.Texture("graphics/uv.png"    , mipmap=False,
#              filter=pi3d.GL_LINEAR, blend=False, m_repeat=True)


# Initialize static geometry -----------------------------------------------

# Transform point lists to eye dimensions
gfxutil.scalePoints(pupilMinPts, vb, eyeRadius)
gfxutil.scalePoints(pupilMaxPts, vb, eyeRadius)
gfxutil.scalePoints(irisPts, vb, eyeRadius)
gfxutil.scalePoints(scleraFrontPts, vb, eyeRadius)
gfxutil.scalePoints(scleraBackPts, vb, eyeRadius)
gfxutil.scalePoints(upperLidClosedPts, vb, eyeRadius)
gfxutil.scalePoints(upperLidOpenPts, vb, eyeRadius)
gfxutil.scalePoints(upperLidEdgePts, vb, eyeRadius)
gfxutil.scalePoints(lowerLidClosedPts, vb, eyeRadius)
gfxutil.scalePoints(lowerLidOpenPts, vb, eyeRadius)
gfxutil.scalePoints(lowerLidEdgePts, vb, eyeRadius)

# Generate initial iris meshes; vertex elements will get replaced on
# a per-frame basis in the main loop, this just sets up textures, etc.
rightIris = gfxutil.meshInit(32, 4, True, 0, 0.5 / iris_map.iy, False)
rightIris.set_textures([iris_map])
rightIris.set_shader(shader)
# Left iris map U value is offset by 0.5; effectively a 180 degree
# rotation, so it's less obvious that the same texture is in use on both.
leftIris = gfxutil.meshInit(32, 4, True, 0.5, 0.5 / iris_map.iy, False)
leftIris.set_textures([iris_map])
leftIris.set_shader(shader)

# Get iris Z depth, for later
irisZ = gfxutil.zangle(irisPts, eyeRadius)[0] * 0.99

# Eyelid meshes are likewise temporary; texture coordinates are
# assigned here but geometry is dynamically regenerated in main loop.
leftUpperEyelid = gfxutil.meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
leftUpperEyelid.set_textures([lidMap])
leftUpperEyelid.set_shader(shader)
leftLowerEyelid = gfxutil.meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
leftLowerEyelid.set_textures([lidMap])
leftLowerEyelid.set_shader(shader)

rightUpperEyelid = gfxutil.meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
rightUpperEyelid.set_textures([lidMap])
rightUpperEyelid.set_shader(shader)
rightLowerEyelid = gfxutil.meshInit(33, 5, False, 0, 0.5/lidMap.iy, True)
rightLowerEyelid.set_textures([lidMap])
rightLowerEyelid.set_shader(shader)

# Generate scleras for each eye...start with a 2D shape for lathing...
angle1 = gfxutil.zangle(scleraFrontPts, eyeRadius)[1]  # Sclera front angle
angle2 = gfxutil.zangle(scleraBackPts, eyeRadius)[1]  # " back angle
aRange = 180 - angle1 - angle2
pts = []
for i in range(24):
    ca, sa = pi3d.Utility.from_polar((90 - angle1) - aRange * i / 23)
    pts.append((ca * eyeRadius, sa * eyeRadius))

# Scleras are generated independently (object isn't re-used) so each
# may have a different image map (heterochromia, corneal scar, or the
# same image map can be offset on one so the repetition isn't obvious).
leftEye = pi3d.Lathe(path=pts, sides=64)
leftEye.set_textures([scleraMap])
leftEye.set_shader(shader)
gfxutil.reAxis(leftEye, 0)

rightEye = pi3d.Lathe(path=pts, sides=64)
rightEye.set_textures([scleraMap])
rightEye.set_shader(shader)
gfxutil.reAxis(rightEye, 0.5)  # Image map offset = 180 degree rotation

# Init global stuff --------------------------------------------------------

rightEye.positionX(-eyePosition)
rightIris.positionX(-eyePosition)
rightUpperEyelid.positionX(-eyePosition)
rightUpperEyelid.positionZ(-eyeRadius - 42)
rightLowerEyelid.positionX(-eyePosition)
rightLowerEyelid.positionZ(-eyeRadius - 42)

leftEye.positionX(eyePosition)
leftIris.positionX(eyePosition)
leftUpperEyelid.positionX(eyePosition)
leftUpperEyelid.positionZ(-eyeRadius - 42)
leftLowerEyelid.positionX(eyePosition)
leftLowerEyelid.positionZ(-eyeRadius - 42)


class TwoEyes(face.Face):
    def __init__(self, left_eye, right_eye, dilator, looker):
        super(TwoEyes, self).__init__()
        self.frames = 0
        self.left_eye = left_eye
        self.right_eye = right_eye
        self.dilator = dilator
        self.looker = looker
        self.left_iris = renderers.IrisRenderer(
            leftIris,
            2.0,
            irisPts,
            irisZ,
            pupilMinPts,
            pupilMaxPts
        )
        self.right_iris = renderers.IrisRenderer(
            rightIris,
            -2.0,
            irisPts,
            irisZ,
            pupilMinPts,
            pupilMaxPts
        )
        self.left_upper_lid = renderers.UpperLidRenderer(
            leftUpperEyelid,
            upperLidOpenPts,
            upperLidClosedPts,
            upperLidEdgePts,
            False
        )
        self.right_upper_lid = renderers.UpperLidRenderer(
            rightUpperEyelid,
            upperLidOpenPts,
            upperLidClosedPts,
            upperLidEdgePts,
            True
        )
        self.left_lower_lid = renderers.LowerLidRenderer(
            leftLowerEyelid,
            lowerLidOpenPts,
            lowerLidClosedPts,
            lowerLidEdgePts,
            False
        )
        self.right_lower_lid = renderers.LowerLidRenderer(
            rightLowerEyelid,
            lowerLidOpenPts,
            lowerLidClosedPts,
            lowerLidEdgePts,
            True
        )

    def frame(self):
        # Generate one frame of imagery

        DISPLAY.loop_running()

        now = time.time()

        self.frames += 1

        curX, curY = self.looker.get_x_y(now)

        p = self.dilator.get_dilation()
        self.left_iris.set_dilation(p)
        self.right_iris.set_dilation(p)

        tracking_pos = 0.3
        if TRACKING:
            n = 0.4 - curY
            tracking_pos = (tracking_pos * 3.0 + n) * 0.25

        left_blink_state = self.left_eye.get_open_amount(now) * 0.75 + 0.25
        self.left_upper_lid.update(left_blink_state, tracking_pos)
        self.left_lower_lid.update(left_blink_state, tracking_pos)

        right_blink_state = self.right_eye.get_open_amount(now) * 0.75 + 0.25
        self.right_upper_lid.update(right_blink_state, tracking_pos)
        self.right_lower_lid.update(right_blink_state, tracking_pos)
        convergence = 2.0

        # change 0.0 - 1.0 to -30 - 30
        curX = (curX * 60) - 30
        curY = (curY * 60) - 30

        # Right eye (on screen left)

        self.right_iris.rotate_to(curX, curY)
        self.right_iris.draw()
        rightEye.rotateToX(curY)
        rightEye.rotateToY(curX - convergence)
        rightEye.draw()

        # Left eye (on screen right)

        self.left_iris.rotate_to(curX, curY)
        self.left_iris.draw()
        leftEye.rotateToX(curY)
        leftEye.rotateToY(curX + convergence)
        leftEye.draw()

        self.left_upper_lid.draw()
        self.left_lower_lid.draw()
        self.right_upper_lid.draw()
        self.right_lower_lid.draw()


def main():
    """Run two eyes."""
    rpi = raspberry.Pi()
    blinker = face.Blinker(rpi.get_blink_state, True)
    left = face.Winker(blinker, rpi.get_wink_l_state)
    right = face.Winker(blinker, rpi.get_wink_r_state)
    if rpi.pupil_pin >= 0:
        dilator = face.AnalogDilator(PUPIL_SMOOTH, PUPIL_IN_FLIP, rpi)
    else:
        dilator = face.FractalDilator()
    if rpi.joystick_x_pin >= 0 and rpi.joystick_y_pin >= 0:
        looker = face.AnalogLooker(JOYSTICK_X_FLIP, JOYSTICK_Y_FLIP, rpi)
    else:
        looker = face.AutonomousLooker()
    two_eyes = TwoEyes(left, right, dilator, looker)

    mykeys = pi3d.Keyboard()  # For capturing key presses
    # MAIN LOOP -- runs continuously
    while True:
        k = mykeys.read()
        if k == 32:
            blinker.close()

        if k == 27:
            # escape
            mykeys.close()
            DISPLAY.stop()
            exit(0)
        try:
            two_eyes.frame()
        except Exception as e:
            print 'Exception', e
            time.sleep(10)


if __name__ == '__main__':
    main()
