"""Things that can render meshes."""
import math

from adafruit.pieyes import gfxutil


class MeshRenderer(object):
    """
    The base class.

    Knows how to accept and draw a mesh.
    """

    def __init__(self, graphics, eye_radius, eye_position, flip_l_r):
        self.graphics = graphics
        self.eye_radius = eye_radius
        self.eye_position = eye_position
        self.flip = flip_l_r
        self.mesh = None
        self.setup_mesh()

    def setup_mesh(self):
        raise NotImplementedError()

    def regenerate(self):
        raise NotImplementedError()

    def draw(self):
        """Just a pass through."""
        self.mesh.draw()


class ConvergedRenderer(MeshRenderer):
    def __init__(self, graphics, eye_radius, eye_position, flip_l_r, convergence):
        if flip_l_r:
            convergence *= -1
            eye_position *= -1
        self.convergence = convergence
        super(ConvergedRenderer, self).__init__(graphics, eye_radius, eye_position, flip_l_r)

    def rotate_to(self, x, y):
        # For some reason, x and y are swapped
        self.mesh.rotateToX(y)
        self.mesh.rotateToY(x + self.convergence)


class ScleraRenderer(ConvergedRenderer):
    def setup_mesh(self):
        self.mesh = self.graphics.get_sclera(self.eye_radius, 0, self.eye_position, 0, 0)

class IrisRenderer(ConvergedRenderer):
    """Render an iris mesh."""
    def __init__(
            self,
            graphics,
            eye_radius,
            eye_position,
            flip_l_r,
            convergence
    ):
        self.iris_points = graphics.get_points("iris")
        self.iris_z = None
        self.u_value = 0
        if flip_l_r:
            # Left iris map U value is offset by 0.5; effectively a 180 degree
            # rotation, so it's less obvious that the same texture is in use on
            # both.
            self.u_value = 0.5
        super(IrisRenderer, self).__init__(graphics, eye_radius, eye_position, flip_l_r, convergence)
        
        self.regen_threshold = 0.0
        self.dilation = -1
        self.prev_pupil_scale = -1
        self.pupil_min_points = graphics.get_points("pupilMin")
        self.pupil_max_points = graphics.get_points("pupilMax")

        # Regenerating flexible object geometry (such as eyelids during blinks,
        # or iris during pupil dilation) is CPU intensive, can noticably slow
        # things down, especially on single-core boards.  To reduce this load
        # somewhat, determine a size change threshold below which regeneration
        # will not occur; roughly equal to 1/4 pixel, since 4x4 area sampling
        # is used.

        # Determine change in pupil size to trigger iris geometry regen
        # Bounds of pupil at min size (in pixels)
        a = gfxutil.pointsBounds(self.pupil_min_points)
        # " at max size
        b = gfxutil.pointsBounds(self.pupil_max_points)

        # motion range in pixels as pupil scales between 0.0 and 1.0
        max_dist = max(
            abs(a[0] - b[0]), abs(a[1] - b[1]),  # Determine distance of max
            abs(a[2] - b[2]), abs(a[3] - b[3])  # variance around each edge
        )
        # 1.0 / max_dist is one pixel's worth of scale range.  Need 1/4 that...
        if max_dist > 0:
            self.regen_threshold = 0.25 / max_dist
        self.regenerate()

    def setup_mesh(self):
        self.iris_z = gfxutil.zangle(self.iris_points, self.eye_radius)[0] * 0.99
        self.mesh = self.graphics.get_iris(self.u_value, self.eye_position, 0, 0)

    def set_dilation(self, dilation):
        """Optionally regenerate iris geometry."""
        # Regenerate iris geometry only if size changed by >= 1/4 pixel
        self.dilation = dilation
        if abs(self.dilation - self.prev_pupil_scale) >= self.regen_threshold:
            self.regenerate()

    def regenerate(self):
        # Interpolate points between min and max pupil sizes
        inter_pupil = gfxutil.pointsInterp(
            self.pupil_min_points,
            self.pupil_max_points,
            self.dilation
        )
        # Generate mesh between interpolated pupil and iris bounds
        mesh = gfxutil.pointsMesh(
            None,
            inter_pupil,
            self.iris_points,
            4,
            -self.iris_z,
            True
        )
        # Assign to both eyes
        self.mesh.re_init(pts=mesh)

    def rotate_to(self, x, y):
        # For some reason, x and y are swapped
        self.mesh.rotateToX(y)
        self.mesh.rotateToY(x + self.convergence)


class LidRenderer(MeshRenderer):

    def __init__(
            self,
            graphics,
            eye_radius,
            eye_position,
            flip_l_r
    ):
        self.lid_z = 0 - eye_radius - 42
        if flip_l_r:
            eye_position *= -1
        super(LidRenderer, self).__init__(graphics, eye_radius, eye_position, flip_l_r)
        self.flip_l_r = flip_l_r

        # Determine change in eyelid values needed to trigger geometry regen.
        # This is done a little differently than the pupils... instead of
        # bounds, the distance between the middle points of the open and closed
        # eyelid  paths is evaluated, then similar 1/4 pixel threshold is
        # determined.
        self.regen_threshold = 0.0
        p1 = self.open_points[int(len(self.open_points) / 2)]
        p2 = self.closed_points[int(len(self.closed_points) / 2)]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        d = dx * dx + dy * dy
        if d > 0:
            self.regen_threshold = 0.25 / math.sqrt(d)

        self.previous_lid_weight = 0.5
        self.lid_weight = 0.5
        self.previous_lid_points = gfxutil.pointsInterp(
            self.open_points,
            self.closed_points,
            self.previous_lid_weight
        )
        self.regenerate()

    def get_new_lid_weight(self, blink_state, tracking_pos):
        raise NotImplementedError

    def update(self, blink_state, tracking_pos):
        self.lid_weight = self.get_new_lid_weight(blink_state, tracking_pos)
        delta_lid_weight = abs(self.lid_weight - self.previous_lid_weight)
        if delta_lid_weight >= self.regen_threshold:
            self.regenerate()

    def regenerate(self):
        new_lid_points = gfxutil.pointsInterp(
            self.open_points,
            self.closed_points,
            self.lid_weight
        )
        if self.lid_weight > self.previous_lid_weight:
            from_points = self.previous_lid_points
            to_points = new_lid_points
        else:
            from_points = new_lid_points
            to_points = self.previous_lid_points

        self.mesh.re_init(
            pts=gfxutil.pointsMesh(
                self.edge_points,
                from_points,
                to_points,
                5,
                0,
                False,
                self.flip_l_r
            )
        )
        self.previous_lid_points = new_lid_points
        self.previous_lid_weight = self.lid_weight


class UpperLidRenderer(LidRenderer):
    def __init__(self, graphics, eye_radius, eye_position, flip_l_r):
        self.closed_points = graphics.get_points("upperLidClosed")
        self.open_points = graphics.get_points("upperLidOpen")
        self.edge_points = graphics.get_points("upperLidEdge")
        super(UpperLidRenderer, self).__init__(graphics, eye_radius, eye_position, flip_l_r)

    def setup_mesh(self):
        self.mesh = self.graphics.get_lid(self.eye_position, 0, self.lid_z)
    
    def get_new_lid_weight(self, blink_state, tracking_pos):
        return tracking_pos + (blink_state * (1.0 - tracking_pos))


class LowerLidRenderer(LidRenderer):
    def __init__(self, graphics, eye_radius, eye_position, flip_l_r):
        self.closed_points = graphics.get_points("lowerLidClosed")
        self.open_points = graphics.get_points("lowerLidOpen")
        self.edge_points = graphics.get_points("lowerLidEdge")
        super(LowerLidRenderer, self).__init__(graphics, eye_radius, eye_position, flip_l_r)

    def setup_mesh(self):
        self.mesh = self.graphics.get_lid(self.eye_position, 0, self.lid_z)
        
    def get_new_lid_weight(self, blink_state, tracking_pos):
        return (1.0 - tracking_pos) + (blink_state * tracking_pos)
