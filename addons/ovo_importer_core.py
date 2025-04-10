# --------------------------------------------------------
#  OVO IMPORTER CORE
# --------------------------------------------------------
# This module provides a high-level "OVOImporter" class that:
#   1) Instantiates the parser (OVOImporterParser) to read the .ovo file.
#   2) Instantiates the scene builder (OVOSceneBuilder) to construct the
#      Blender scene based on the parsed data.
#   3) Orchestrates the overall process and returns a status to Blender.
# --------------------------------------------------------

import os

# Attempt to import from relative paths if running as an addon.
try:
    from .ovo_importer_parser import OVOImporterParser
    from .ovo_importer_builder import OVOSceneBuilder
except ImportError:
    # Fallback for non-addon environments.
    from ovo_importer_parser import OVOImporterParser
    from ovo_importer_builder import OVOSceneBuilder


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
        print(f"[OVOImporter] Starting import of {self.filepath}")

        # Step 1: Parse the file.
        parser = OVOImporterParser(self.filepath)
        if not parser.parse_file():
            print("[OVOImporter] Error: parse_file() returned False - file not found or error occurred.")
            return {'CANCELLED'}

        # Step 2: Build the Blender scene.
        # Assumes texture files are located in the same directory as the .ovo file.
        texture_dir = os.path.dirname(self.filepath)
        builder = OVOSceneBuilder(
            node_records=parser.node_records,
            materials=parser.materials,
            texture_directory=texture_dir
        )
        builder.build_scene()

        print("[OVOImporter] Import completed successfully.")
        return {'FINISHED'}
