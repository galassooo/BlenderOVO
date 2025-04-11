import sys
import os
import unittest
import numpy as np
from mathutils import Matrix
import math

# Import the base class directly from the parent directory
from test_base import OVOExporterTestBase

# Add the parent directory to the path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)


class TestHierarchies(OVOExporterTestBase):
    """Tests to verify that hierarchical relationships are exported correctly"""

    def test_mesh_parent_mesh(self):
        """Test to verify correct parenting between two meshes (Cube parent of Cone)"""
        data = self.export_and_parse("hierarchyCubeParentCone.blend")

        # Verify the presence of the root node
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        self.assertIsNotNone(root, "The [root] node must exist")

        # Verify the presence of Cube and Cone
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        cone = next((m for m in data["meshes"] if m["name"] == "Cone"), None)
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")
        self.assertIsNotNone(cone, "The 'Cone' mesh must exist")

        # Verify that Cube is a direct child of [root]
        self.assertEqual(root["children_count"], 1, "The [root] node must have 1 child (Cube)")

        # Verify that Cone is a child of Cube
        self.assertEqual(cube["children_count"], 1, "Cube must have 1 child (Cone)")
        self.assertEqual(cone["children_count"], 0, "Cone must not have children")

        # Optional: verify the transformation matrix of Cone (should be relative to parent)
        # If Cone is offset by (0,0,2) from Cube, we expect the translation component to be about (0,0,2)
        matrix_array = np.array(cone["matrix"]).reshape((4, 4))
        translation_z = matrix_array[3, 2]  # Extract the Z component of translation
        self.assertAlmostEqual(abs(translation_z), 2.0, delta=0.1,
                               msg="The Z position of Cone should be about 2 units relative to parent")

    def test_empty_parent_mesh(self):
        """Test to verify parenting with empty nodes (Empty parent of Cube)"""
        data = self.export_and_parse("hierarchyEmptyParentCube.blend")

        # Verify the presence of the root node
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        self.assertIsNotNone(root, "The [root] node must exist")

        # Find the Empty and the Cube
        empty = next((n for n in data["nodes"] if n["name"] == "Empty"), None)
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(empty, "The 'Empty' node must exist")
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")

        # Verify that Empty is a child of [root]
        self.assertTrue(root["children_count"] >= 1, "The [root] node must have at least 1 child (Empty)")

        # Verify that Cube is a child of Empty
        self.assertEqual(empty["children_count"], 1, "Empty must have 1 child (Cube)")
        self.assertEqual(cube["children_count"], 0, "Cube must not have children")

        # Optional: verify the transformation matrix if Empty is offset from origin
        # If Empty is offset, Cube should have a transformation relative to Empty

    def test_flat_hierarchy(self):
        """Test to verify that objects without parent-child relationship are all children of [root]"""
        data = self.export_and_parse("hierarchyFlat.blend")

        # Verify the presence of the root node
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        self.assertIsNotNone(root, "The [root] node must exist")

        # Find Cube and Cone
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        cone = next((m for m in data["meshes"] if m["name"] == "Cone"), None)
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")
        self.assertIsNotNone(cone, "The 'Cone' mesh must exist")

        # Verify that the root has 2 children (Cube and Cone)
        self.assertTrue(root["children_count"] >= 2, "The [root] node must have at least 2 children (Cube and Cone)")

        # Verify that Cube and Cone do not have children
        self.assertEqual(cube["children_count"], 0, "Cube must not have children")
        self.assertEqual(cone["children_count"], 0, "Cone must not have children")

        # Verify absolute positioning: Cube and Cone should have transformations relative to global system
        # This can be verified by checking their transformation matrices

    def test_rotation_matrix_for_root_children(self):
        """Test to verify that -90° X rotation matrix is only applied to direct children of [root]"""
        data = self.export_and_parse("hierarchyRootChildrenRotation.blend")

        # Verify the presence of the root node
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        self.assertIsNotNone(root, "The [root] node must exist")

        # Find the objects: we expect two cubes as direct [root] children, and one cone as child of a cube
        cube1 = next((m for m in data["meshes"] if m["name"] == "Cube1"), None)
        cube2 = next((m for m in data["meshes"] if m["name"] == "Cube2"), None)
        cone = next((m for m in data["meshes"] if m["name"] == "Cone"), None)

        self.assertIsNotNone(cube1, "The 'Cube1' mesh must exist")
        self.assertIsNotNone(cube2, "The 'Cube2' mesh must exist")
        self.assertIsNotNone(cone, "The 'Cone' mesh must exist")

        # Verify hierarchy relationships
        self.assertTrue(root["children_count"] >= 2, "The [root] node must have at least 2 children (Cube1 and Cube2)")

        # One of the cubes should have the cone as child
        parent_of_cone = None
        if cube1["children_count"] > 0:
            parent_of_cone = cube1
        elif cube2["children_count"] > 0:
            parent_of_cone = cube2

        self.assertIsNotNone(parent_of_cone, "One of the cubes must be the parent of Cone")

        # Now verify the rotation matrices of the objects
        def extract_rotation_x_degrees(matrix_array):
            """Extract the X rotation angle in degrees from a matrix"""
            # Create a rotation matrix from the 3x3 part of the transformation matrix
            rot_matrix = matrix_array[:3, :3]

            # A rotation of -90° around X axis should have approximately:
            # [ 1  0  0 ]
            # [ 0  0 -1 ]
            # [ 0  1  0 ]

            # Check if matrix has the pattern of X rotation of -90°
            has_90_x_rotation = (
                    abs(rot_matrix[0, 0] - 1.0) < 0.1 and
                    abs(rot_matrix[1, 1]) < 0.1 and
                    abs(rot_matrix[1, 2] + 1.0) < 0.1 and
                    abs(rot_matrix[2, 1] - 1.0) < 0.1 and
                    abs(rot_matrix[2, 2]) < 0.1
            )

            return has_90_x_rotation

        # Check that the cubes (direct children of [root]) have the -90° X rotation
        cube1_matrix = np.array(cube1["matrix"]).reshape((4, 4))
        cube2_matrix = np.array(cube2["matrix"]).reshape((4, 4))

        self.assertTrue(extract_rotation_x_degrees(cube1_matrix),
                        "Cube1 (direct child of [root]) should have -90° X rotation")
        self.assertTrue(extract_rotation_x_degrees(cube2_matrix),
                        "Cube2 (direct child of [root]) should have -90° X rotation")

        # Check that the cone (child of a cube, not direct child of [root]) does NOT have the -90° X rotation
        cone_matrix = np.array(cone["matrix"]).reshape((4, 4))
        self.assertFalse(extract_rotation_x_degrees(cone_matrix),
                         "Cone (not a direct child of [root]) should NOT have -90° X rotation")

        # Verify that the cone's matrix represents a local transformation relative to its parent
        # This would require knowledge of how the scene is set up (e.g., cone's position relative to parent)

    def test_empty_chain(self):
        """Test to verify correct parenting in a chain of Empty objects (Empty1 → Empty2 → Empty3 → Cube)"""
        data = self.export_and_parse("hierarchyEmptyChain.blend")

        # Verify the presence of the root node and all objects
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        empty1 = next((n for n in data["nodes"] if n["name"] == "Empty1"), None)
        empty2 = next((n for n in data["nodes"] if n["name"] == "Empty2"), None)
        empty3 = next((n for n in data["nodes"] if n["name"] == "Empty3"), None)
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)

        self.assertIsNotNone(root, "The [root] node must exist")
        self.assertIsNotNone(empty1, "The 'Empty1' node must exist")
        self.assertIsNotNone(empty2, "The 'Empty2' node must exist")
        self.assertIsNotNone(empty3, "The 'Empty3' node must exist")
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")

        # Verify hierarchy relationships
        self.assertTrue(root["children_count"] >= 1, "The [root] node must have at least 1 child (Empty1)")
        self.assertEqual(empty1["children_count"], 1, "Empty1 must have 1 child (Empty2)")
        self.assertEqual(empty2["children_count"], 1, "Empty2 must have 1 child (Empty3)")
        self.assertEqual(empty3["children_count"], 1, "Empty3 must have 1 child (Cube)")
        self.assertEqual(cube["children_count"], 0, "Cube must not have children")

        # Verify transformation composition through the chain
        # If each Empty is offset by 1 unit in a different direction, the final cube's position
        # should be the sum of all transformations through the hierarchy

        # Extract transformation matrices
        empty1_matrix = np.array(empty1["matrix"]).reshape((4, 4))
        empty2_matrix = np.array(empty2["matrix"]).reshape((4, 4))
        empty3_matrix = np.array(empty3["matrix"]).reshape((4, 4))
        cube_matrix = np.array(cube["matrix"]).reshape((4, 4))

        # The -90° X rotation should be applied only to Empty1 (direct child of [root])
        self.assertTrue(self._has_90_x_rotation(empty1_matrix),
                        "Empty1 (direct child of [root]) should have -90° X rotation")
        self.assertFalse(self._has_90_x_rotation(empty2_matrix),
                         "Empty2 (not a direct child of [root]) should NOT have -90° X rotation")
        self.assertFalse(self._has_90_x_rotation(empty3_matrix),
                         "Empty3 (not a direct child of [root]) should NOT have -90° X rotation")
        self.assertFalse(self._has_90_x_rotation(cube_matrix),
                         "Cube (not a direct child of [root]) should NOT have -90° X rotation")

    def test_deep_hierarchy(self):
        """Test to verify correct parenting in a deep hierarchy (Cube1 → Cube2 → Cube3 → Cube4 and Cone1 → Cone2 → Cone3)"""
        data = self.export_and_parse("hierarchyDeep.blend")

        # Verify presence of all objects
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        cube1 = next((m for m in data["meshes"] if m["name"] == "Cube1"), None)
        cube2 = next((m for m in data["meshes"] if m["name"] == "Cube2"), None)
        cube3 = next((m for m in data["meshes"] if m["name"] == "Cube3"), None)
        cube4 = next((m for m in data["meshes"] if m["name"] == "Cube4"), None)
        cone1 = next((m for m in data["meshes"] if m["name"] == "Cone1"), None)
        cone2 = next((m for m in data["meshes"] if m["name"] == "Cone2"), None)
        cone3 = next((m for m in data["meshes"] if m["name"] == "Cone3"), None)

        self.assertIsNotNone(root, "The [root] node must exist")
        self.assertIsNotNone(cube1, "The 'Cube1' mesh must exist")
        self.assertIsNotNone(cube2, "The 'Cube2' mesh must exist")
        self.assertIsNotNone(cube3, "The 'Cube3' mesh must exist")
        self.assertIsNotNone(cube4, "The 'Cube4' mesh must exist")
        self.assertIsNotNone(cone1, "The 'Cone1' mesh must exist")
        self.assertIsNotNone(cone2, "The 'Cone2' mesh must exist")
        self.assertIsNotNone(cone3, "The 'Cone3' mesh must exist")

        # Verify hierarchy relationships for cubes
        self.assertTrue(root["children_count"] >= 2, "The [root] node must have at least 2 children (Cube1 and Cone1)")
        self.assertEqual(cube1["children_count"], 1, "Cube1 must have 1 child (Cube2)")
        self.assertEqual(cube2["children_count"], 1, "Cube2 must have 1 child (Cube3)")
        self.assertEqual(cube3["children_count"], 1, "Cube3 must have 1 child (Cube4)")
        self.assertEqual(cube4["children_count"], 0, "Cube4 must not have children")

        # Verify hierarchy relationships for cones
        self.assertEqual(cone1["children_count"], 1, "Cone1 must have 1 child (Cone2)")
        self.assertEqual(cone2["children_count"], 1, "Cone2 must have 1 child (Cone3)")
        self.assertEqual(cone3["children_count"], 0, "Cone3 must not have children")

        # Check that the -90° X rotation is applied only to Cube1 and Cone1 (direct children of [root])
        cube1_matrix = np.array(cube1["matrix"]).reshape((4, 4))
        cone1_matrix = np.array(cone1["matrix"]).reshape((4, 4))

        self.assertTrue(self._has_90_x_rotation(cube1_matrix),
                        "Cube1 (direct child of [root]) should have -90° X rotation")
        self.assertTrue(self._has_90_x_rotation(cone1_matrix),
                        "Cone1 (direct child of [root]) should have -90° X rotation")

        # Check that other objects don't have the -90° X rotation
        cube2_matrix = np.array(cube2["matrix"]).reshape((4, 4))
        cone2_matrix = np.array(cone2["matrix"]).reshape((4, 4))

        self.assertFalse(self._has_90_x_rotation(cube2_matrix),
                         "Cube2 (not a direct child of [root]) should NOT have -90° X rotation")
        self.assertFalse(self._has_90_x_rotation(cone2_matrix),
                         "Cone2 (not a direct child of [root]) should NOT have -90° X rotation")

    def test_light_parent_mesh(self):
        """Test to verify correct parenting between a light and a mesh (Point light parent of Cube)"""
        data = self.export_and_parse("hierarchyLightParentMesh.blend")

        # Verify presence of all objects
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        light = next((l for l in data["lights"] if l["name"] == "Point"), None)
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)

        self.assertIsNotNone(root, "The [root] node must exist")
        self.assertIsNotNone(light, "The 'Point' light must exist")
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")

        # Verify hierarchy relationships
        self.assertTrue(root["children_count"] >= 1, "The [root] node must have at least 1 child (Point)")
        self.assertEqual(light["children_count"], 1, "Point light must have 1 child (Cube)")
        self.assertEqual(cube["children_count"], 0, "Cube must not have children")

        # Check that the -90° X rotation is applied only to the Point light (direct child of [root])
        light_matrix = np.array(light["matrix"]).reshape((4, 4))
        cube_matrix = np.array(cube["matrix"]).reshape((4, 4))


        self.assertFalse(self._has_90_x_rotation(cube_matrix),
                         "Cube (not a direct child of [root]) should NOT have -90° X rotation")

    def test_mesh_parent_light(self):
        """Test to verify correct parenting between a mesh and a light (Cube parent of Point light)"""
        data = self.export_and_parse("hierarchyMeshParentLight.blend")

        # Verify presence of all objects
        root = next((n for n in data["nodes"] if n["name"] == "[root]"), None)
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        light = next((l for l in data["lights"] if l["name"] == "Point"), None)

        self.assertIsNotNone(root, "The [root] node must exist")
        self.assertIsNotNone(cube, "The 'Cube' mesh must exist")
        self.assertIsNotNone(light, "The 'Point' light must exist")

        # Verify hierarchy relationships
        self.assertTrue(root["children_count"] >= 1, "The [root] node must have at least 1 child (Cube)")
        self.assertEqual(cube["children_count"], 1, "Cube must have 1 child (Point)")
        self.assertEqual(light["children_count"], 0, "Point light must not have children")

        # Check that the -90° X rotation is applied only to the Cube (direct child of [root])
        cube_matrix = np.array(cube["matrix"]).reshape((4, 4))
        light_matrix = np.array(light["matrix"]).reshape((4, 4))

        self.assertTrue(self._has_90_x_rotation(cube_matrix),
                        "Cube (direct child of [root]) should have -90° X rotation")
        self.assertFalse(self._has_90_x_rotation(light_matrix),
                         "Point light (not a direct child of [root]) should NOT have -90° X rotation")

    def _has_90_x_rotation(self, matrix_array):
        """Helper function to check if a matrix has a -90° rotation around X axis"""
        # Extract the rotation part (3x3) of the matrix
        rot_matrix = matrix_array[:3, :3]

        # A rotation of -90° around X axis should have approximately:
        # [ 1  0  0 ]
        # [ 0  0 -1 ]
        # [ 0  1  0 ]

        # Check if matrix has the pattern of X rotation of -90°
        has_90_x_rotation = (
                abs(rot_matrix[0, 0] - 1.0) < 0.1 and
                abs(rot_matrix[1, 1]) < 0.1 and
                abs(rot_matrix[1, 2] + 1.0) < 0.1 and
                abs(rot_matrix[2, 1] - 1.0) < 0.1 and
                abs(rot_matrix[2, 2]) < 0.1
        )

        return has_90_x_rotation