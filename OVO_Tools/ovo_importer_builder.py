# --------------------------------------------------------
#  OVO IMPORTER BUILDER
# --------------------------------------------------------
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

import os
import bpy
import mathutils

from .ovo_types import HullType, LightType
from .ovo_mesh_factory import MeshFactory
from .ovo_light_factory import LightFactory
from .ovo_node_factory import NodeFactory

class OVOSceneBuilder:
    """
    Builds a Blender scene from parsed importer data.

    Attributes:
        node_records (list): List of NodeRecord objects (for NODE, MESH, LIGHT).
        materials (dict): Dictionary mapping material names to OVOMaterial objects.
        texture_directory (str): Base folder to search for texture files.
        record_to_object (dict): Maps each NodeRecord to its created Blender object.
    """

    def __init__(self, node_records, materials, texture_directory):
        """
        Initialize with parsed data.

        :param node_records: A list of NodeRecord objects containing parsed node information.
        :param materials: A dictionary of material data keyed by material name.
        :param texture_directory: The directory where texture files are located.
        """
        self.node_records = node_records
        self.materials = materials
        self.texture_directory = texture_directory
        self.record_to_object = {}

    def build_scene(self):
        """
        Main entry point to build the Blender scene.

        Steps:
          1) For each NodeRecord, create an object using the appropriate factory.
          2) Build parent–child relationships using a stack-based approach.
          3) Establish a [root] node if multiple top-level nodes exist.
          4) Apply final transformations (transpose, rotations, quaternion corrections).
        """
        # Create a Blender object for each node record using factories.
        for rec in self.node_records:
            if rec.node_type == "MESH":
                obj = MeshFactory.create(rec, self.materials, self.texture_directory)
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

        print("[OVOSceneBuilder] Scene build complete!")

    # The _build_hierarchy, _establish_root_node, and _apply_transformations
    # methods remain unchanged as they deal with structuring and transforming
    # the scene rather than object creation.
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
            print("[OVOSceneBuilder] Multiple top-level nodes detected; creating [root].")
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
          - For LIGHT nodes, quaternion correction is applied based on the light’s parsed direction.
        """
        def log_info(message, indent=0):
            prefix = "  " * indent
            print(f"{prefix}{message}")

        log_info("[OVOImporter] Applying transformations.")

        for rec in self.node_records:
            if rec.name == "[root]":
                log_info("Skipping [root] node.", indent=1)
                continue

            obj = self.record_to_object.get(rec)
            if not obj:
                log_info(f"Node '{rec.name}' has no associated Blender object. Skipping.", indent=1)
                continue

            mat = mathutils.Matrix(rec.raw_matrix)
            mat.transpose()  # Now in Blender's column-major format

            if obj.parent and obj.parent.name == "[root]":
                conv_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                mat = conv_90_x @ mat
                log_info(f"Extra +90° X rotation applied to '{rec.name}' because parent is [root].", indent=1)

            if rec.node_type == "LIGHT":
                if rec.light_type == LightType.DIRECTIONAL:
                    if rec.light_quat is None:
                        default_dir = mathutils.Vector((0, 0, -1))
                        target_dir = mathutils.Vector(rec.direction).normalized()
                        rec.light_quat = default_dir.rotation_difference(target_dir)
                        log_info(f"Computed light_quat for '{rec.name}' from direction {rec.direction}.", indent=2)
                if rec.light_quat:
                    loc, base_rot, scale = mat.decompose()
                    log_info(f"Light '{rec.name}' decomposition:", indent=1)
                    log_info(f"  Location = {loc}", indent=2)
                    log_info(f"  Base rotation (Euler) = {base_rot.to_euler('XYZ')}", indent=2)
                    log_info(f"  Scale = {scale}", indent=2)
                    corrected_rot = rec.light_quat @ base_rot
                    log_info(f"Corrected rotation (Euler) = {corrected_rot.to_euler('XYZ')}", indent=2)
                    final_mat = corrected_rot.to_matrix().to_4x4()
                    final_mat[0][0] *= scale.x
                    final_mat[1][1] *= scale.y
                    final_mat[2][2] *= scale.z
                    final_mat[0][3] = loc.x
                    final_mat[1][3] = loc.y
                    final_mat[2][3] = loc.z
                    obj.matrix_basis = final_mat
                    log_info(f"Final transformation for light '{rec.name}' applied: {final_mat.to_euler('XYZ')}", indent=1)
                    continue

            obj.matrix_basis = mat
