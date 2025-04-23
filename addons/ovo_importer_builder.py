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
import math

import bpy
import mathutils

from .ovo_types import LightType
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

        print("[OVOSceneBuilder] Scene build complete!")
        print(f"[OVOSceneBuilder] Textures {'flipped' if self.flip_textures else 'not flipped'} during import")

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
        Uses the conversion method similar to what's used in the exporter.
        """
        # Matrice di conversione tra sistemi di coordinate OpenGL e Blender
        C = mathutils.Matrix((
            (1, 0, 0, 0),
            (0, 0, 1, 0),
            (0, -1, 0, 0),
            (0, 0, 0, 1)
        ))
        C_inv = C.transposed()

        for rec in self.node_records:
            if rec.name == "[root]": continue
            obj = self.record_to_object.get(rec)
            if not obj: continue

            # 1) row→col-major
            mat = mathutils.Matrix(rec.raw_matrix).transposed()

            # 2) similarity transform OpenGL→Blender (per tutti gli oggetti, non solo figli di [root])
            transformed_mat = C_inv @ mat @ C

            # Debug delle matrici
            print(f"\nOggetto: {rec.name}")
            print("Matrice originale (trasposta da raw):")
            for row in mat:
                print(f"  {row[0]:.4f}, {row[1]:.4f}, {row[2]:.4f}, {row[3]:.4f}")

            print("Matrice trasformata:")
            for row in transformed_mat:
                print(f"  {row[0]:.4f}, {row[1]:.4f}, {row[2]:.4f}, {row[3]:.4f}")

            # Estrai decomposizione per debug
            loc, rot, scale = transformed_mat.decompose()
            print(f"Posizione: {loc}")
            print(f"Rotazione (euler): {rot.to_euler('XYZ')}")
            print(f"Scala: {scale}")

            # 3) applica matrix_basis
            obj.matrix_basis = transformed_mat

    # --------------------------------------------------
    #  Apply Final Transformations
    # --------------------------------------------------
    def _fix_matrix_for_blender(self, matrix):
        """
        Converts a matrix from OpenGL coordinate system back to Blender.

        This is the inverse operation of what the exporter does:
        1. Swap the Y and Z columns
        2. Invert the sign of the new Y column (which was the Z column)

        Args:
            matrix (mathutils.Matrix): The matrix to convert

        Returns:
            mathutils.Matrix: The transformed matrix
        """
        # Make a copy to avoid modifying the original
        matrix = matrix.copy()

        # Swap column 1 (Y) with column 2 (Z)
        tmp = matrix[1].copy()
        matrix[1] = matrix[2]
        matrix[2] = tmp

        # Invert the sign of the new column 1 (Y) which was originally column 2 (Z)
        matrix[1] = -matrix[1]

        return matrix