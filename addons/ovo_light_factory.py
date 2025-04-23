# ================================================================
#  LIGHT FACTORY
# ================================================================
# This module defines the LightFactory class responsible for creating
# Blender Light objects based on the parsed LIGHT data from a NodeRecord.
# ================================================================
import math
import mathutils
import bpy


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
            # Trasforma la direzione della luce da coordinate OpenGL a coordinate Blender
            transformed_direction = LightFactory.transform_direction(rec.direction)

            # Per debug
            print(f"Luce '{rec.name}' direzione (originale): {rec.direction}")
            print(f"Luce '{rec.name}' direzione (trasformata): {transformed_direction}")

        return light_obj

    @staticmethod
    def transform_direction(direction):
        """
        Trasforma un vettore direzione dal sistema di coordinate OpenGL al sistema Blender.

        Args:
            direction (mathutils.Vector): Vettore direzione originale

        Returns:
            mathutils.Vector: Vettore direzione trasformato
        """
        if not direction:
            return mathutils.Vector((0, 0, -1))

        # Crea la matrice di conversione (3x3 per vettori direzione)
        C = mathutils.Matrix((
            (1, 0, 0),
            (0, 0, 1),
            (0, -1, 0)
        ))
        C_inv = C.transposed()  # Inverso per convertire da OpenGL a Blender

        # Applica trasformazione inversa
        dir_vec = mathutils.Vector(direction)
        transformed = C_inv @ dir_vec

        # Ritorna vettore normalizzato
        return transformed.normalized()
