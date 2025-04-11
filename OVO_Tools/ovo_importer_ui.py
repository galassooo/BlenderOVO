# --------------------------------------------------------
# IMPORTER UI MODULE
# --------------------------------------------------------
# This module defines the Blender Operator (OT_ImportOVO) for
# importing an OVO file. When executed, it passes the selected
# file path to the high-level importer (OVOImporter) and updates
# the scene so that imported objects are visible.
#
# It also provides a menu function to add this operator to the
# File → Import menu.
# ================================================================

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from bpy.types import Operator

# If running as an addon (with relative imports), it will import via .ovo_importer_core;
# otherwise, it falls back to a direct import.
try:
    from .ovo_importer_core import OVOImporter
except ImportError:
    from ovo_importer_core import OVOImporter

class OT_ImportOVO(Operator, ImportHelper):
    """Operator to import an OVO file into Blender."""
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"

    # Set the expected file extension.
    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        """
        Execute the operator:
          1. Instantiate the high-level OVOImporter with the chosen filepath.
          2. Call its import_scene() method which parses the file and builds the scene.
          3. Update the scene view and return 'FINISHED' (or 'CANCELLED' on error).
        """
        importer = OVOImporter(self.filepath)
        result = importer.import_scene()
        # Ensure the view layer is updated so the imported objects show up.
        bpy.context.view_layer.update()
        return result

def menu_func_import_importer(self, context):
    """
    Adds this operator to the File → Import menu in Blender.
    When the user selects "OverVision Object (.ovo)", it will invoke OT_ImportOVO.
    """
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")
