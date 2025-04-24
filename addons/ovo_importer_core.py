# ================================================================
#  OVO IMPORTER CORE
# ================================================================
# This module provides a high-level "OVOImporter" class that:
#   1) Instantiates the parser (OVOImporterParser) to read the .ovo file.
#   2) Instantiates the scene builder (OVOSceneBuilder) to construct the
#      Blender scene based on the parsed data.
#   3) Orchestrates the overall process and returns a status to Blender.
# ================================================================

# --------------------------------------------------------
# Imports
# --------------------------------------------------------
import os
import bpy

try:
    from .ovo_importer_parser import OVOImporterParser
    from .ovo_importer_builder import OVOSceneBuilder
    from .ovo_log import log
except ImportError:
    from ovo_importer_parser import OVOImporterParser
    from ovo_importer_builder import OVOSceneBuilder
    from ovo_log import log

# --------------------------------------------------------
# OVO Importer Class
# --------------------------------------------------------
class OVOImporter:
    """
    High-level importer class that is called by the UI operator to import an OVO file.

    The import process consists of two main steps:
      1. Parsing the .ovo file to extract materials and node records.
      2. Building the Blender scene using the extracted data.
    """

    def __init__(self, filepath: str):
        """
        Initialize the importer with the path to the .ovo file.

        :param filepath: Full file path to the .ovo file.
        """
        self.filepath = filepath

        # Set True by default and overridden by the UI operator
        self.flip_textures = True

    # --------------------------------------------------------
    # Import Scene
    # --------------------------------------------------------
    def import_scene(self):
        """
        Main entry point to import the OVO file into Blender.

        Steps:
          1) Create an instance of OVOImporterParser and call parse_file().
             - If parsing fails (e.g. file not found), return {'CANCELLED'}.
          2) Instantiate OVOSceneBuilder with the parsed node records and materials,
             along with the texture directory.
          3) Call the builder's build_scene() to create Blender objects.
          4) Return {'FINISHED'} to indicate a successful import.

        :return: A dictionary with the status, either {'FINISHED'} or {'CANCELLED'}.
        """
        log("", category="")
        log("============================================================", category="")
        log(f"[OVOImporter] Starting import of {self.filepath}", category="")

        # Step 1: Parse the file.
        parser = OVOImporterParser(self.filepath)
        if not parser.parse_file():
            log("[OVOImporter] Error: parse_file() returned False - file not found or error occurred.",category="ERROR", indent=1)
            return {'CANCELLED'}

        # Step 2: Build the Blender scene.
        texture_dir = os.path.dirname(self.filepath)
        builder = OVOSceneBuilder(
            node_records=parser.node_records,
            materials=parser.materials,
            texture_directory=texture_dir,
            flip_textures=self.flip_textures
        )

        builder.build_scene()

        log("[OVOImporter] Import completed successfully.", category="NODE")
        log("============================================================\n", category="")
        return {'FINISHED'}