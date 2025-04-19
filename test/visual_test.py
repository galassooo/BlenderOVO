#!/usr/bin/env python3
"""
Visual Comparison Tests for OVO Exporter/Importer.

This script provides visual testing for the OVO exporter/importer workflow:
1. Loads Blender scenes
2. Captures reference images
3. Exports to OVO format
4. Imports back into Blender
5. Captures result images
6. Compares images to verify visual consistency
7. Generates an HTML report with results

Designed to be run from Blender's Python environment.
"""

import os
import sys
import unittest
import bpy
import tempfile
import shutil
import glob
import math
from pathlib import Path
import contextlib
import io

# Add parent directory to path if needed
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Try to import image comparison libraries
try:
    import numpy as np
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("PIL not available. Visual tests will be limited.")

# Try to import OVO Importer
try:
    from OVO_Tools.ovo_importer_core import OVOImporter

    HAS_OVO_IMPORTER = True
except ImportError:
    try:
        # Alternative import path
        from addons.ovo_importer_core import OVOImporter

        HAS_OVO_IMPORTER = True
    except ImportError:
        HAS_OVO_IMPORTER = False
        print("OVO Importer not found. Tests will be limited.")


@contextlib.contextmanager
def captured_output():
    """Context manager for suppressing stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = stdout, stderr
        yield stdout, stderr
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def export_ovo(output_path, use_mesh=True, use_light=True, use_legacy_compression=True, suppress_output=True):
    """Exports the current scene to OVO format."""
    try:
        if suppress_output:
            with captured_output():
                bpy.ops.export_scene.ovo(
                    filepath=output_path,
                    use_mesh=use_mesh,
                    use_light=use_light,
                    use_legacy_compression=use_legacy_compression
                )
        else:
            bpy.ops.export_scene.ovo(
                filepath=output_path,
                use_mesh=use_mesh,
                use_light=use_light,
                use_legacy_compression=use_legacy_compression
            )
        return True
    except Exception as e:
        print(f"Error during export: {e}")
        return False


class VisualTest(unittest.TestCase):
    """Visual comparison tests for OVO format."""

    def setUp(self):
        """Setup test directories and parameters."""
        # Base directories
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.scenes_dir = os.path.join(self.test_dir, "scenes")
        self.output_dir = os.path.join(self.test_dir, "output")

        # Output subdirectories
        self.reference_dir = os.path.join(self.output_dir, "reference_images")
        self.temp_dir = os.path.join(self.output_dir, "temp_screenshots")
        self.report_dir = os.path.join(self.output_dir, "visual_reports")

        # Metadata directory
        self.metadata_dir = os.path.join(self.scenes_dir, "metadata")

        # Create directories
        for directory in [self.output_dir, self.reference_dir,
                          self.temp_dir, self.report_dir, self.metadata_dir]:
            os.makedirs(directory, exist_ok=True)

        # Test parameters
        self.pixel_threshold = 0.10  # 10% difference threshold
        self.report_data = []

        # Skip if PIL is not available
        if not HAS_PIL:
            self.skipTest("PIL is not available, required for visual tests")

        # Skip if OVO Importer is not available
        if not HAS_OVO_IMPORTER:
            self.skipTest("OVO Importer not available, required for tests")

    def tearDown(self):
        """Generate the unified report."""
        if hasattr(self, 'report_data') and self.report_data:
            self._generate_unified_report()

    def setup_camera_for_test(self, location=(10, -10, 10), rotation=(60, 0, 45)):
        """Sets up a standard test camera."""
        # Create a new camera if it doesn't exist
        if 'TestCamera' not in bpy.data.objects:
            cam_data = bpy.data.cameras.new("TestCamera")
            cam_obj = bpy.data.objects.new("TestCamera", cam_data)
            bpy.context.collection.objects.link(cam_obj)
        else:
            cam_obj = bpy.data.objects['TestCamera']

        # Position the camera
        cam_obj.location = location
        cam_obj.rotation_euler = (
            math.radians(rotation[0]),
            math.radians(rotation[1]),
            math.radians(rotation[2])
        )

        # Set camera as active
        bpy.context.scene.camera = cam_obj
        bpy.context.view_layer.update()

        return cam_obj

    def capture_screenshot(self, filepath, camera_setup=True):
        """Captures a screenshot via rendering."""
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Set up camera if requested
        if camera_setup:
            self.setup_camera_for_test()

        # Configure rendering
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 64
        scene.cycles.max_bounces = 4

        # Ensure materials render correctly
        for material in bpy.data.materials:
            if material.use_nodes:
                material.blend_method = 'OPAQUE'

        # Set resolution
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
        scene.render.film_transparent = False
        scene.render.filepath = filepath

        # Render
        bpy.ops.render.render(write_still=True)
        return filepath

    def compare_images(self, test_image_path, reference_image_path, threshold=None):
        """Compares two images and calculates the difference percentage."""
        if not HAS_PIL:
            self.fail("PIL not available, required for image comparison")

        # Use default threshold if not specified
        if threshold is None:
            threshold = self.pixel_threshold

        # Load the images
        try:
            test_img = Image.open(test_image_path)
            ref_img = Image.open(reference_image_path)
        except Exception as e:
            self.fail(f"Error loading images: {str(e)}")

        # Check dimensions
        if test_img.size != ref_img.size:
            test_img = test_img.resize(ref_img.size)
            test_img.save(test_image_path)

        # Convert to numpy arrays
        test_array = np.array(test_img)
        ref_array = np.array(ref_img)

        # Calculate difference directly between full images
        abs_diff = np.abs(test_array.astype(np.float32) - ref_array.astype(np.float32))
        diff_percentage = np.mean(abs_diff) / 255.0

        # Create difference image
        diff_image_path = test_image_path.replace(".png", "_diff.png")

        # Create a visualization based on the reference image with differences highlighted in red
        if len(ref_array.shape) == 3 and ref_array.shape[2] >= 3:
            # For RGB images - convert reference to grayscale
            ref_gray = np.dot(ref_array[..., :3], [0.2989, 0.5870, 0.1140]).astype(np.uint8)

            #creo versione rgb della grayscale
            diff_img = np.zeros((ref_array.shape[0], ref_array.shape[1], 3), dtype=np.uint8)
            for c in range(3):
                diff_img[:, :, c] = ref_gray

            # Calculate significant differences
            significant_threshold = 40
            r_diff = np.abs(test_array[:, :, 0].astype(np.int16) - ref_array[:, :, 0].astype(np.int16))
            g_diff = np.abs(test_array[:, :, 1].astype(np.int16) - ref_array[:, :, 1].astype(np.int16))
            b_diff = np.abs(test_array[:, :, 2].astype(np.int16) - ref_array[:, :, 2].astype(np.int16))
            significant_diff = (r_diff > significant_threshold) | (g_diff > significant_threshold) | (
                        b_diff > significant_threshold)

            # Mark significant differences in red
            diff_img[:, :, 0][significant_diff] = 255 #R
            diff_img[:, :, 1][significant_diff] = 0#G
            diff_img[:, :, 2][significant_diff] = 0# B
        else:
            # For grayscale images
            #creo rgb da grayscale x result
            diff_img = np.zeros((ref_array.shape[0], ref_array.shape[1], 3), dtype=np.uint8)
            for c in range(3):
                diff_img[:, :, c] = ref_array

            #calc differenza
            channel_diff = np.abs(test_array.astype(np.int16) - ref_array.astype(np.int16))
            significant_diff = channel_diff > 40

            # Mark differences in red
            diff_img[:, :, 0][significant_diff] = 255#R
            diff_img[:, :, 1][significant_diff] = 0 #G
            diff_img[:, :, 2][significant_diff] = 0 #B

        # Save difference image
        Image.fromarray(diff_img.astype(np.uint8)).save(diff_image_path)

        is_similar = diff_percentage <= threshold
        return is_similar, diff_percentage, diff_image_path

    def read_scene_metadata(self, scene_name):
        """Reads metadata for a scene from a text file."""
        # Default values
        default_metadata = {
            # Transformations
            'scaling': 0,
            'rotation': 0,
            'translation': 0,

            # Lights
            'pointLight': 0,
            'sunLight': 0,
            'spotLight': 0,
            'lightDirectionRotated': 0,
            'colorLight': 0,

            # Materials
            'albedo': 0,
            'normalMap': 0,
            'roughness': 0,
            'metallic': 0,

            'material': 0,

            # Other features
            'lod': 0,
            'emptyNodes': 0,
            'hierarchy': 0
        }

        # Check for metadata file
        metadata_path = os.path.join(self.metadata_dir, f"{scene_name}_metadata.txt")
        if not os.path.exists(metadata_path):
            return default_metadata

        # Parse metadata file
        metadata = default_metadata.copy()
        try:
            with open(metadata_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Parse key=value line
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # Convert value to boolean/integer
                        if value.lower() in ('1', 'true', 'yes'):
                            metadata[key] = 1
                        elif value.lower() in ('0', 'false', 'no'):
                            metadata[key] = 0
        except Exception as e:
            print(f"Error reading metadata for {scene_name}: {str(e)}")

        return metadata

    def get_active_features(self, metadata):
        """Returns list of active features in metadata."""
        return [key for key, value in metadata.items() if value == 1]

    def add_to_report(self, test_name, ref_path, test_path, diff_path, is_similar, diff_percentage, metadata=None):
        """Adds test results to the unified report."""
        # Copy images to report directory with standardized names
        ref_report_path = os.path.join(self.report_dir, f"{test_name}_reference.png")
        test_report_path = os.path.join(self.report_dir, f"{test_name}_result.png")
        diff_report_path = os.path.join(self.report_dir, f"{test_name}_diff.png")

        shutil.copy2(ref_path, ref_report_path)
        shutil.copy2(test_path, test_report_path)
        if diff_path:
            shutil.copy2(diff_path, diff_report_path)

        self.report_data.append({
            'test_name': test_name,
            'ref_path': os.path.basename(ref_report_path),
            'test_path': os.path.basename(test_report_path),
            'diff_path': os.path.basename(diff_report_path) if diff_path else None,
            'is_similar': is_similar,
            'diff_percentage': diff_percentage,
            'metadata': metadata or {}
        })

    def _generate_unified_report(self):
        """Generates HTML report with all test results."""
        if not self.report_data:
            return

        # Calculate statistics
        total_tests = len(self.report_data)
        passed_tests = sum(1 for item in self.report_data if item['is_similar'])

        # Create HTML report
        html_report_path = os.path.join(self.report_dir, f"unified_report.html")

        with open(html_report_path, 'w') as f:
            f.write(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>OVO Tools Visual Test Report</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1, h2, h3 {{ color: #333; }}
                    .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                    .pass {{ color: green; }}
                    .fail {{ color: red; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                    .test-row {{ margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #ccc; }}

                    .image-container {{ 
                        display: flex; 
                        justify-content: space-between; 
                        margin-top: 10px; 
                    }}

                    .image-box {{ 
                        width: 32%; 
                        text-align: center; 
                    }}

                    .image-box img {{ 
                        max-width: 100%; 
                        border: 1px solid #ccc; 
                    }}

                    .progress-bar {{ 
                        background-color: #f0f0f0; 
                        height: 20px; 
                        border-radius: 10px; 
                        margin-top: 10px; 
                    }}

                    .progress {{ 
                        background-color: {('#4CAF50' if passed_tests == total_tests else '#FFC107' if passed_tests > 0 else '#F44336')}; 
                        height: 100%; 
                        border-radius: 10px; 
                        width: {(passed_tests / total_tests * 100) if total_tests > 0 else 0}%; 
                    }}

                    .metadata-tags {{
                        display: flex;
                        flex-wrap: wrap;
                        gap: 5px;
                        margin-top: 10px;
                    }}

                    .metadata-tag {{
                        padding: 3px 8px;
                        border-radius: 12px;
                        background-color: #e0e0e0;
                        font-size: 0.8em;
                    }}
                </style>
            </head>
            <body>
                <h1>OVO Tools Visual Test Report</h1>
                <div class="summary">
                    <h2>Summary</h2>
                    <p>Tests completed: {total_tests}</p>
                    <p>Tests passed: <span class="{'pass' if passed_tests == total_tests else 'fail'}">{passed_tests}/{total_tests} ({(
                    passed_tests / total_tests * 100) if total_tests > 0 else 0:.1f}%)</span></p>
                    <div class="progress-bar">
                        <div class="progress"></div>
                    </div>
                </div>
            """)

            # Add results table
            f.write("""
                <h2>Detailed Results</h2>
                <table>
                    <tr>
                        <th>Test</th>
                        <th>Status</th>
                        <th>Difference</th>
                        <th>Features</th>
                    </tr>
            """)

            # Add table rows
            for item in self.report_data:
                metadata = item.get('metadata', {})
                active_features = self.get_active_features(metadata)
                features_str = ", ".join(active_features) if active_features else "None"

                f.write(f"""
                    <tr>
                        <td>{item['test_name']}</td>
                        <td class="{'pass' if item['is_similar'] else 'fail'}">{('PASSED' if item['is_similar'] else 'FAILED')}</td>
                        <td>{item['diff_percentage'] * 100:.2f}%</td>
                        <td>{features_str}</td>
                    </tr>
                """)

            f.write("</table>\n\n")

            # Add detailed sections for each test with images
            for item in self.report_data:
                metadata = item.get('metadata', {})
                active_features = self.get_active_features(metadata)

                f.write(f"""
                <div class="test-row">
                    <h3>{item['test_name']} - <span class="{'pass' if item['is_similar'] else 'fail'}">{('PASSED' if item['is_similar'] else 'FAILED')}</span></h3>
                    <p>Difference: {item['diff_percentage'] * 100:.2f}%</p>
                """)

                # Add metadata tags
                if active_features:
                    f.write('<div class="metadata-tags">')
                    for feature in active_features:
                        f.write(f'<span class="metadata-tag">{feature}</span>')
                    f.write('</div>')

                f.write(f"""
                    <div class="image-container">
                        <div class="image-box">
                            <h4>Reference Image</h4>
                            <img src="{item['ref_path']}" alt="Reference">
                        </div>
                        <div class="image-box">
                            <h4>Test Result</h4>
                            <img src="{item['test_path']}" alt="Result">
                        </div>
                        <div class="image-box">
                            <h4>Differences</h4>
                            <img src="{item['diff_path']}" alt="Differences">
                        </div>
                    </div>
                </div>
                """)

            f.write("""
            </body>
            </html>
            """)

        print(f"Unified report generated: {html_report_path}")
        return html_report_path

    def run_single_file_test(self, blend_file):
        """Runs a complete export-import test with visual verification."""
        test_name = Path(blend_file).stem
        print(f"\n=== Running test for: {test_name} ===")

        # Read metadata
        metadata = self.read_scene_metadata(test_name)
        active_features = self.get_active_features(metadata)

        if active_features:
            print(f"Scene features: {', '.join(active_features)}")
        else:
            print("No special features defined for this scene")

        # Create temporary file for OVO export
        with tempfile.NamedTemporaryFile(suffix=".ovo", delete=False) as temp_file:
            temp_ovo_path = temp_file.name

        try:
            # PHASE 1: Load the blend and generate reference
            print(f"Loading file: {blend_file}")
            with captured_output():
                bpy.ops.wm.open_mainfile(filepath=blend_file)

            # Setup camera and capture reference
            self.setup_camera_for_test()
            ref_image_path = os.path.join(self.reference_dir, f"{test_name}_reference.png")
            print(f"Generating reference image: {ref_image_path}")
            self.capture_screenshot(ref_image_path)

            # PHASE 2: Export to OVO
            print(f"Exporting to OVO: {temp_ovo_path}")
            export_success = export_ovo(temp_ovo_path, suppress_output=True)
            if not export_success:
                raise RuntimeError(f"OVO export failed for {test_name}")

            # PHASE 3: Clean scene and import OVO
            print("Cleaning scene and importing OVO")
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete()

            importer = OVOImporter(temp_ovo_path)
            importer.flip_textures = True  # Ensure textures are flipped the same way
            result = importer.import_scene()
            if result != {'FINISHED'}:
                raise RuntimeError(f"OVO import failed for {test_name}")

            # PHASE 4: Capture test result
            test_image_path = os.path.join(self.temp_dir, f"{test_name}_result.png")
            print(f"Capturing result screenshot: {test_image_path}")
            self.capture_screenshot(test_image_path)

            # PHASE 5: Compare images
            print("Comparing images...")
            is_similar, diff_percentage, diff_image_path = self.compare_images(
                test_image_path, ref_image_path
            )

            # PHASE 6: Add to report
            self.add_to_report(
                test_name,
                ref_image_path,
                test_image_path,
                diff_image_path,
                is_similar,
                diff_percentage,
                metadata
            )

            print(f"Test completed: {'PASSED' if is_similar else 'FAILED'}")
            print(f"Difference: {diff_percentage * 100:.2f}%")

            return is_similar

        except Exception as e:
            print(f"ERROR during test of {test_name}: {str(e)}")
            import traceback
            traceback.print_exc()

            # Add error entry to report
            placeholder_img = os.path.join(self.report_dir, "error.png")
            # Create a simple error image if it doesn't exist
            if not os.path.exists(placeholder_img):
                img = Image.new('RGB', (400, 300), color=(255, 0, 0))
                img.save(placeholder_img)

            self.add_to_report(
                test_name,
                placeholder_img,
                placeholder_img,
                None,
                False,
                1.0,
                metadata
            )
            return False

        finally:
            # Clean up
            if os.path.exists(temp_ovo_path):
                os.unlink(temp_ovo_path)

    def test_all_blend_files(self):
        """Tests all .blend files in the scenes directory."""
        # Find all .blend files
        blend_files = glob.glob(os.path.join(self.scenes_dir, "*.blend"))

        # If no files found, report error
        if not blend_files:
            self.fail(f"No .blend files found in {self.scenes_dir}")

        print(f"Found {len(blend_files)} .blend files to test")

        # Test each file
        results = {}
        for blend_file in blend_files:
            file_name = os.path.basename(blend_file)
            print(f"\n=== Test for {file_name} ===")

            try:
                result = self.run_single_file_test(blend_file)
                results[file_name] = result
            except Exception as e:
                print(f"Error during test of {file_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                results[file_name] = False

        # Print summary
        print("\n=== TEST SUMMARY ===")
        passed = sum(1 for result in results.values() if result)
        total = len(results)

        for file_name, passed_test in results.items():
            status = "PASSED" if passed_test else "FAILED"
            print(f"{file_name}: {status}")

        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"\nTotal: {passed}/{total} tests passed ({success_rate:.1f}%)")

        # Assert all tests passed
        self.assertEqual(passed, total, f"{total - passed} tests failed. See the report for details.")


# This allows running the test directly from Blender's Python console or via command line
if __name__ == "__main__":
    unittest.main()