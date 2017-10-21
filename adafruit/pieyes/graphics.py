from xml.dom.minidom import parse

import pi3d

from adafruit.pieyes import gfxutil


def camel_case(snake_cased):
    """Get camel case string for simple strings."""
    title_cased = snake_cased.title().replace("_", "")
    return title_cased[0].lower() + title_cased[1:]


def get_texture(texture_path, blend):
    """Load a texture image into a pi3d texture."""
    return pi3d.Texture(
        texture_path,
        mipmap=False,
        filter=pi3d.GL_LINEAR,
        blend=blend
    )


class EyeGraphics(object):
    # name: (number_points, closed, reversed)
    layers = {
        'pupil_min': {
            'number_points': 32,
            'closed': True,
            'reversed': True
        },
        'pupil_max': {
            'number_points': 32,
            'closed': True,
            'reversed': True
        },
        'iris': {
            'number_points': 32,
            'closed': True,
            'reversed': True
        },
        'sclera_front': {
            'number_points': 0,
            'closed': False,
            'reversed': False
        },
        'sclera_back': {
            'number_points': 0,
            'closed': False,
            'reversed': False
        },
        'upper_lid_closed': {
            'number_points': 33,
            'closed': False,
            'reversed': True
        },
        'upper_lid_open': {
            'number_points': 33,
            'closed': False,
            'reversed': True
        },
        'upper_lid_edge': {
            'number_points': 33,
            'closed': False,
            'reversed': False
        },
        'lower_lid_closed': {
            'number_points': 33,
            'closed': False,
            'reversed': False
        },
        'lower_lid_open': {
            'number_points': 33,
            'closed': False,
            'reversed': False
        },
        'lower_lid_edge': {
            'number_points': 33,
            'closed': False,
            'reversed': False
        }
    }

    def __init__(self, svg_path, texture_data):
        """Load SVG file, extract paths & convert to point lists"""
        self.dom = parse(svg_path)
        self.texture_data = texture_data
        self.shader = pi3d.Shader("uv_light")


        self.points = {}
        self.camel_points = {}
        for layer, properties in self.layers.items():
            layer_id = camel_case(layer)
            pts = gfxutil.getPoints(
                self.dom,
                layer_id,
                properties['number_points'],
                properties['closed'],
                properties['reversed']
            )
            self.points[layer] = pts
            self.camel_points[layer_id] = pts
        self.textures = {}
        for texture, texture_args in self.texture_data.items():
            texture_path, blend = texture_args
            self.textures[texture] = get_texture(texture_path, blend)

    def get_texture(self, texture):
        return self.textures[texture]

    def set_eye_radius(self, eye_radius):
        """Set the scale for each set of points."""
        view_box = gfxutil.getViewBox(self.dom)
        for pts in self.points.values():
            gfxutil.scalePoints(pts, view_box, eye_radius)

    def get_points(self, layer):
        if layer in self.points:
            return self.points[layer]
        elif layer in self.camel_points:
            return self.camel_points[layer]
        else:
            raise ValueError('No points for %s' % layer)

    def get_iris(self, u_offset, x, y, z):
        properties = self.layers['iris']
        texture = self.get_texture('iris')
        mesh = gfxutil.meshInit(
            properties['number_points'],
            4,
            properties['closed'],
            u_offset,
            0.5 / texture.iy,
            False
        )
        mesh.set_textures([texture])
        mesh.set_shader(self.shader)
        mesh.position(x, y, z)
        return mesh

    def get_lid(self, x, y, z):
        properties = self.layers['upper_lid_open']
        texture = self.get_texture('lid')
        mesh = gfxutil.meshInit(
            properties['number_points'],
            5,
            properties['closed'],
            0,
            0.5 / texture.iy,
            True
        )
        mesh.set_textures([texture])
        mesh.set_shader(self.shader)
        mesh.position(x, y, z)
        return mesh

    def get_sclera(self, eye_radius, offset, x, y, z):
        """Generate sclera."""
        # start with a 2D shape for lathing
        # Sclera front angle
        angle1 = gfxutil.zangle(
            self.points['sclera_front'], eye_radius)[1]

        # Sclera back angle
        angle2 = gfxutil.zangle(
            self.points['sclera_back'], eye_radius)[1]
        angle_range = 180 - angle1 - angle2
        pts = []
        for i in range(24):
            ca, sa = pi3d.Utility.from_polar(
                (90 - angle1) - angle_range * i / 23
            )
            pts.append((ca * eye_radius, sa * eye_radius))

        # Scleras are generated independently (object isn't re-used) so
        # each may have a different image map (heterochromia, corneal scar, or
        # the same image map can be offset on one so the repetition
        # isn't obvious).
        sclera = pi3d.Lathe(path=pts, sides=64)
        sclera.set_textures([self.get_texture('sclera')])
        sclera.set_shader(self.shader)
        sclera.position(x, y, z)
        gfxutil.reAxis(sclera, offset)
        return sclera
