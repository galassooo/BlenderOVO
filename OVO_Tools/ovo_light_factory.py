# ================================================================
#  LIGHT FACTORY
# ================================================================
# This module defines the LightFactory class responsible for creating
# Blender Light objects based on the parsed LIGHT data from a NodeRecord.
# ================================================================

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
        ldata.energy = rec.radius * 10
        ldata.use_shadow = bool(rec.shadow)
        if rec.light_type == 2:
            ldata.spot_size = rec.cutoff
            ldata.spot_blend = rec.spot_exponent / 10.0

        light_obj = bpy.data.objects.new(rec.name, ldata)
        if not light_obj.users_collection:
            bpy.context.collection.objects.link(light_obj)
        return light_obj
