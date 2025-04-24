# ================================================================
#  LIGHT FACTORY
# ================================================================
# This module defines the LightFactory class responsible for creating
# Blender Light objects based on the parsed LIGHT data from a NodeRecord.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import math
import mathutils
import bpy

# --------------------------------------------------------
# Light Factory
# --------------------------------------------------------
class LightFactory:
    """
    LightFactory creates Blender Light objects from NodeRecord data representing lights.

    It maps the numeric light type from the input data to the appropriate Blender
    light type, sets the light properties such as color and energy, and returns a
    configured light object.
    """

    @staticmethod
    def create(rec):
        if rec.light_type == 0:
            ldata = bpy.data.lights.new(rec.name, type='POINT')
        elif rec.light_type == 1:
            ldata = bpy.data.lights.new(rec.name, type='SUN')
        elif rec.light_type == 2:
            ldata = bpy.data.lights.new(rec.name, type='SPOT')
        else:
            ldata = bpy.data.lights.new(rec.name, type='POINT')

        # Set basic light properties.
        ldata.color = rec.color
        ldata.energy = 10
        ldata.use_shadow = bool(rec.shadow)
        if rec.light_type == 1:
            ldata.angle = rec.cutoff
        if rec.light_type == 2:
            ldata.spot_size = math.radians(rec.radius)
            ldata.spot_blend = rec.spot_exponent / 10.0

        light_obj = bpy.data.objects.new(rec.name, ldata)
        if not light_obj.users_collection:
            bpy.context.collection.objects.link(light_obj)

        if rec.light_type in [1, 2] and rec.direction:
            # Transform direction from OpenGL coordinates to Blender coordinates
            transformed_direction = LightFactory.transform_direction(rec.direction)

            # Per debug
            print(f"Luce '{rec.name}' direzione (originale): {rec.direction}")
            print(f"Luce '{rec.name}' direzione (trasformata): {transformed_direction}")
        return light_obj

    @staticmethod
    def transform_direction(direction):
        """
        Transform a direction vector from OpenGL system to Blender system

        Args:
            direction (mathutils.Vector): Original direction vector

        Returns:
            mathutils.Vector: Transformed direction vector
        """
        if not direction:
            return mathutils.Vector((0, 0, -1))

        # Conversion matrix (3x3 per direction vectors)
        C = mathutils.Matrix((
            (1, 0, 0),
            (0, 0, 1),
            (0, -1, 0)
        ))
        C_inv = C.transposed()  # Inverse to convert from OpenGL to Blender

        dir_vec = mathutils.Vector(direction)
        transformed = C_inv @ dir_vec

        return transformed.normalized()