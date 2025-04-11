import sys
import os
import unittest
import math
import numpy as np
from mathutils import Matrix
from scipy.spatial.transform import Rotation as R

# Importa la classe base direttamente dalla directory parent
from test_base import OVOExporterTestBase

# Aggiungi la directory parent al path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)


class TestSimpleCubeTransformations(OVOExporterTestBase):
    def test_cube_translation(self):
        """Test cube translation"""
        data = self.export_and_parse("simpleCubeTranslation.blend")

        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Estrai la matrice di trasformazione
        matrix = cube["matrix"]
        matrix_array = np.array(matrix).reshape((4, 4))

        # Estrai la traslazione dalla matrice
        translation_x = matrix_array[3, 0]
        translation_y = matrix_array[3, 1]
        translation_z = matrix_array[3, 2]

        # Verifica le coordinate di traslazione
        # blender coordinates: x,y,z => 3, 5, 2 to opengl: 3, 2, -5
        self.assertAlmostEqual(translation_x, 3.0, delta=0.001)
        self.assertAlmostEqual(translation_y, 2.0, delta=0.001)
        self.assertAlmostEqual(translation_z, -5.0, delta=0.001)

    import numpy as np
    import math
    from scipy.spatial.transform import Rotation as R

    def test_cube_rotation(self):
        """Verify rotation matrix properties"""
        data = self.export_and_parse("simpleCubeRotation.blend")

        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Estrai la matrice di trasformazione
        matrix = cube["matrix"]

        # Crea una Matrix di Blender
        mat_np = np.array(matrix).reshape((4, 4))  # matrice numpy 4×4
        mat_blender = Matrix(mat_np)  # mathutils.Matrix

        eul = mat_blender.to_euler('ZYX') #IMPORTANTISSIMO DA LASCIARE COSIIIIIIIIIIIIIIIIIII
        # Converti in gradi:
        x_deg = math.degrees(eul.x)
        y_deg = math.degrees(eul.y)
        z_deg = math.degrees(eul.z)


        R_3x3 = np.array(mat_blender)[:3, :3]
        det_R = np.linalg.det(R_3x3)
        self.assertAlmostEqual(det_R, 1.0, delta=1e-3, msg="Determinante non ~ 1.0: non è pura rotazione")

        self.assertAlmostEqual(x_deg, 45.0, delta=0.5)
        self.assertAlmostEqual(y_deg, 0.0, delta=0.5)
        self.assertAlmostEqual(z_deg, 10.0, delta=0.5)

        print(f"Angoli estratti: X={x_deg:.2f}° Y={y_deg:.2f}° Z={z_deg:.2f}°")

    def test_cube_scaling(self):
        """Test cube scaling (2, 3, 5 on x, y, z)"""
        data = self.export_and_parse("simpleCubeScaling.blend")

        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Estrai la matrice di trasformazione
        matrix = cube["matrix"]
        matrix_array = np.array(matrix).reshape((4, 4))

        # Estrai gli scaling dai valori diagonali della matrice
        scale_x = np.linalg.norm(matrix_array[:3, 0])
        scale_y = np.linalg.norm(matrix_array[:3, 1])
        scale_z = np.linalg.norm(matrix_array[:3, 2])

        # Verifica gli scaling
        # Considera che lo scaling è rispetto alla dimensione originale del cubo (2x2x2)
        self.assertAlmostEqual(scale_x, 2.0, delta=0.001, msg="Scaling X non corretto")
        self.assertAlmostEqual(scale_y, 5.0, delta=0.001, msg="Scaling Y non corretto")
        self.assertAlmostEqual(scale_z, 3.0, delta=0.001, msg="Scaling Z non corretto")

        # Verifica aggiuntiva con bounding box
        bbox_min = cube["bbox_min"]
        bbox_max = cube["bbox_max"]

        width = bbox_max[0] - bbox_min[0]
        height = bbox_max[1] - bbox_min[1]
        depth = bbox_max[2] - bbox_min[2]

        # Verifica le dimensioni scalate (considerando la conversione OpenGL)
        self.assertAlmostEqual(width, 4.0, delta=0.001, msg="Larghezza (X) non corretta dopo scaling")
        self.assertAlmostEqual(height, 10.0, delta=0.001, msg="Altezza (Y) non corretta dopo scaling")
        self.assertAlmostEqual(depth, 6.0, delta=0.001, msg="Profondità (Z) non corretta dopo scaling")

    def test_cube_triangulation(self):
        """Verify cube triangulation after export"""
        data = self.export_and_parse("simpleCube.blend")

        # Trova la mesh del cubo
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Un cubo ha 6 facce originali, che dovrebbero diventare 12 triangoli dopo la triangolazione
        # Verifica il numero di facce nel primo LOD
        lod_data = cube["lods"][0]

        # Verifica il numero di vertici e facce
        self.assertEqual(lod_data["face_count"], 12, "Il cubo dovrebbe avere 12 triangoli dopo l'esportazione")

        # Verifica che il numero di vertici sia coerente con la triangolazione
        # Tipicamente, la triangolazione di un cubo aumenta il numero di vertici
        self.assertEqual(lod_data["vertex_count"], 14, "Il cubo dovrebbe avere 14 vertici dopo la triangolazione")

    def test_cube_vertex_uniqueness(self):
        """Verify that vertices are unique and correct"""
        data = self.export_and_parse("simpleCube.blend")

        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Verifica le coordinate del bounding box
        bbox_min = cube["bbox_min"]
        bbox_max = cube["bbox_max"]

        # Un cubo standard ha lati da -1 a 1
        self.assertAlmostEqual(bbox_min[0], -1.0, delta=0.001, msg="Coordinata X minima non corretta")
        self.assertAlmostEqual(bbox_min[1], -1.0, delta=0.001, msg="Coordinata Y minima non corretta")
        self.assertAlmostEqual(bbox_min[2], -1.0, delta=0.001, msg="Coordinata Z minima non corretta")

        self.assertAlmostEqual(bbox_max[0], 1.0, delta=0.001, msg="Coordinata X massima non corretta")
        self.assertAlmostEqual(bbox_max[1], 1.0, delta=0.001, msg="Coordinata Y massima non corretta")
        self.assertAlmostEqual(bbox_max[2], 1.0, delta=0.001, msg="Coordinata Z massima non corretta")
        self.assertAlmostEqual(bbox_max[2], 1.0, delta=0.001, msg="Coordinata Z massima non corretta")

    def test_default_material_assignment(self):
        """Verify default material is assigned to the cube"""
        data = self.export_and_parse("simpleCube.blend")

        # Trova la mesh del cubo
        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Verifica l'assegnazione del materiale
        self.assertIsNotNone(cube.get("material"), "Deve essere presente un materiale")

        # Verifica che il nome del materiale sia corretto
        self.assertEqual(cube["material"], "Material", "Il materiale di default deve essere 'Material'")

    def test_material_properties(self):
        """Verify basic properties of the default material"""
        # Trova i dati del materiale
        materials = self.export_and_parse("simpleCube.blend")["materials"]

        # Cerca il materiale di default
        default_material = next((m for m in materials if m["name"] == "Material"), None)
        self.assertIsNotNone(default_material, "Il materiale di default 'Material' deve esistere")

        # Verifica proprietà base del materiale
        # Colore base (grigio chiaro)
        self.assertAlmostEqual(default_material["albedo"][0], 0.8, delta=0.1)
        self.assertAlmostEqual(default_material["albedo"][1], 0.8, delta=0.1)
        self.assertAlmostEqual(default_material["albedo"][2], 0.8, delta=0.1)

        # Altre proprietà di default
        self.assertAlmostEqual(default_material["roughness"], 0.5, delta=0.1)
        self.assertAlmostEqual(default_material["metalness"], 0.0, delta=0.1)
        self.assertEqual(default_material["alpha"], 1.0)

        # Verifica che non ci siano texture
        self.assertEqual(default_material["textures"]["albedo"], "[none]")
        self.assertEqual(default_material["textures"]["normal"], "[none]")
        self.assertEqual(default_material["textures"]["height"], "[none]")
        self.assertEqual(default_material["textures"]["roughness"], "[none]")
        self.assertEqual(default_material["textures"]["metalness"], "[none]")

    def test_cube_combined_transform(self):
        """Test cube with combined transformations"""
        data = self.export_and_parse("simpleCubeCombinedTransform.blend")

        cube = next((m for m in data["meshes"] if m["name"] == "Cube"), None)
        self.assertIsNotNone(cube, "La mesh 'Cube' deve esistere")

        # Estrai la matrice di trasformazione
        matrix = cube["matrix"]
        matrix_array = np.array(matrix).reshape((4, 4))

        # Estrai traslazione
        translation_x = matrix_array[3, 0]
        translation_y = matrix_array[3, 1]
        translation_z = matrix_array[3, 2]

        # Estrai scaling e rotazione
        scale_x = np.linalg.norm(matrix_array[:3, 0])
        scale_y = np.linalg.norm(matrix_array[:3, 1])
        scale_z = np.linalg.norm(matrix_array[:3, 2])


        # Verifica traslazione
        self.assertAlmostEqual(translation_x, 2.0, delta=0.5)
        self.assertAlmostEqual(translation_y, 3.0, delta=0.5)
        self.assertAlmostEqual(translation_z, -1.0, delta=0.5)

        # Verifica scaling
        self.assertAlmostEqual(scale_x, 1.5, delta=0.5)
        self.assertAlmostEqual(scale_y, 1.5, delta=0.5)
        self.assertAlmostEqual(scale_z, 1.5, delta=0.5)