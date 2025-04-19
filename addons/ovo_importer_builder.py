# ================================================================
#  OVO IMPORTER BUILDER
# ================================================================
# This module converts NodeRecord objects (parsed from the .ovo file)
# into actual Blender objects. It delegates object creation to dedicated
# factories:
#   - MeshFactory for MESH nodes,
#   - LightFactory for LIGHT nodes,
#   - NodeFactory for generic nodes.
#
# It then builds the parent–child hierarchy, creates a root if needed,
# and applies final transformations.
# ================================================================

# --------------------------------------------------------
# Imports
# --------------------------------------------------------
import math

import bpy
import mathutils

try:
    from .ovo_types import LightType
    from .ovo_mesh_factory import MeshFactory
    from .ovo_light_factory import LightFactory
    from .ovo_node_factory import NodeFactory
    from .ovo_log import log
except ImportError:
    from ovo_types import LightType
    from ovo_mesh_factory import MeshFactory
    from ovo_light_factory import LightFactory
    from ovo_node_factory import NodeFactory
    from ovo_log import log

# --------------------------------------------------------
# OVO SCENE BUILDER CLASS
# --------------------------------------------------------
class OVOSceneBuilder:
    """
    Builds a Blender scene from parsed importer data.

    Attributes:
        node_records (list): List of NodeRecord objects (for NODE, MESH, LIGHT).
        materials (dict): Dictionary mapping material names to OVOMaterial objects.
        texture_directory (str): Base folder to search for texture files.
        flip_textures (bool): Whether to flip textures vertically.
        record_to_object (dict): Maps each NodeRecord to its created Blender object.
    """

    def __init__(self, node_records, materials, texture_directory, flip_textures=True):
        """
        Initialize with parsed data.

        :param node_records: A list of NodeRecord objects containing parsed node information.
        :param materials: A dictionary of material data keyed by material name.
        :param texture_directory: The directory where texture files are located.
        :param flip_textures: Whether to flip textures vertically.
        """
        self.node_records = node_records
        self.materials = materials
        self.texture_directory = texture_directory
        self.flip_textures = flip_textures
        self.record_to_object = {}

    # --------------------------------------------------------
    # Build Scene
    # --------------------------------------------------------
    def build_scene(self):
        """
        Main entry point to build the Blender scene.

        Steps:
          1) For each NodeRecord, create an object using the appropriate factory.
          2) Build parent–child relationships using a stack-based approach.
          3) Establish a [root] node if multiple top-level nodes exist.
          4) Apply final transformations (transpose, rotations, quaternion corrections).
        """
        log("", category="")
        log("============================================================", category="")
        log("[OVOSceneBuilder] Starting scene build from parsed nodes", category="")
        log("============================================================", category="")

        # Create a Blender object for each node record using factories.
        for rec in self.node_records:
            if rec.node_type == "MESH":
                obj = MeshFactory.create(rec, self.materials, self.texture_directory, flip_textures=self.flip_textures)
            elif rec.node_type == "LIGHT":
                obj = LightFactory.create(rec)
            else:
                # Use NodeFactory for generic nodes.
                obj = NodeFactory.create(rec)
            self.record_to_object[rec] = obj

        # Build the hierarchy (parent–child relationships).
        self._build_hierarchy()

        # Establish a root node if more than one top-level node exists.
        self._establish_root_node()

        # Apply final transformations for proper orientation.
        self._apply_transformations()

        log("", category="")
        log("[OVOSceneBuilder] Scene build complete", category="")
        flip_status = "flipped" if self.flip_textures else "not flipped"
        log(f"Textures were {flip_status} during import", category="")
        log("============================================================", category="")

    # --------------------------------------------------
    #  Build Hierarchy
    # --------------------------------------------------
    def _build_hierarchy(self):
        """
        Creates parent-child relationships among the NodeRecord objects.

        Uses a stack-based approach:
          - Iterates over all NodeRecord objects.
          - Assigns a parent for each child based on the 'children_count'.
          - Decreases the parent's children_count as children are assigned.
        """
        stack = []
        for rec in self.node_records:
            while stack and stack[-1].children_count == 0:
                stack.pop()

            if stack:
                parent_rec = stack[-1]
                rec_obj = self.record_to_object[rec]
                par_obj = self.record_to_object[parent_rec]
                rec_obj.parent = par_obj
                parent_rec.children_count -= 1

            if rec.children_count > 0:
                stack.append(rec)

    # --------------------------------------------------
    #  Establish Root Node
    # --------------------------------------------------
    def _establish_root_node(self):
        """
        Checks if multiple top-level nodes exist. If so, creates a fake "[root]"
        empty object and parents all top-level objects to it.
        """
        top_records = [rec for rec in self.node_records if not self.record_to_object[rec].parent]
        if len(top_records) > 1:
            log("[OVOSceneBuilder] Multiple top-level nodes detected; creating [root].", category="NODE")
            root_obj = bpy.data.objects.new("[root]", None)
            root_obj.empty_display_type = 'PLAIN_AXES'
            bpy.context.collection.objects.link(root_obj)

            for rec in top_records:
                self.record_to_object[rec].parent = root_obj

    # --------------------------------------------------
    #  Apply Final Transformations
    # --------------------------------------------------
    def _apply_transformations(self):
        """
        Finalizes the scene by applying the correct object transformations.
        For each NodeRecord:
          - Converts the raw_matrix (list of 4-tuples, row-major) to a mathutils.Matrix.
          - Transposes it to obtain Blender's column-major matrix.
          - If the object is parented to a "[root]" object, an extra rotation may be applied.
          - For LIGHT nodes, quaternion correction is applied based on the light's parsed direction.
        """
        log("[OVOSceneBuilder] Applying transformations...", category="")

        for rec in self.node_records:
            if rec.name == "[root]":
                log("Skipping [root] node.", category="NODE", indent=1)
                continue

            obj = self.record_to_object.get(rec)
            if not obj:
                log(f"Node '{rec.name}' has no associated Blender object. Skipping.", category="NODE", indent=1)
                continue

            mat = mathutils.Matrix(rec.raw_matrix)
            mat.transpose()  # Now in Blender's column-major format

            if obj.parent and obj.parent.name == "[root]":
                # Apply an extra +90° X rotation to match Blender's orientation
                conv_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                mat = conv_90_x @ mat
                log(f"Extra +90° X rotation applied to '{rec.name}' (parent is [root])", category="NODE", indent=1)

            if rec.node_type == "LIGHT":
                obj.matrix_basis = mat

                if rec.light_type in (LightType.DIRECTIONAL, LightType.SPOT):
                    rot_matrix = mat.to_3x3()

                    euler = rot_matrix.to_euler('ZYX')

                    x_deg = math.degrees(euler.x)
                    y_deg = math.degrees(euler.y)
                    z_deg = math.degrees(euler.z)

                    log(f"Light '{rec.name}' rotation (ZYX): X={x_deg:.2f}°, Y={y_deg:.2f}°, Z={z_deg:.2f}°",category="LIGHT", indent=1)
                continue

            obj.matrix_basis = mat