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
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

# If running as an addon (with relative imports), it will import via .ovo_importer_core;
# otherwise, it falls back to a direct import.
try:
    from .ovo_importer_core import OVOImporter
    from .ovo_material_factory import MaterialFactory
except ImportError:
    from ovo_importer_core import OVOImporter
    from ovo_material_factory import MaterialFactory


class OT_ImportOVO(Operator, ImportHelper):
    """Operator to import an OVO file into Blender."""
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"

    # Set the expected file extension.
    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    flip_textures: BoolProperty(
        name="Flip Textures",
        description="Flip textures vertically during import",
        default=True
    )

    def execute(self, context):
        """
        Execute the operator:
          1. Instantiate the high-level OVOImporter with the chosen filepath.
          2. Call its import_scene() method which parses the file and builds the scene.
          3. Update the scene view and return 'FINISHED' (or 'CANCELLED' on error).
        """
        print(f"[OT_ImportOVO] Starting import of {self.filepath}")
        print(f"[OT_ImportOVO] Flip textures: {self.flip_textures}")

        importer = OVOImporter(self.filepath)

        # Pass the flag for the textures
        importer.flip_textures = self.flip_textures

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


# Cleanup handler - registered when the addon is enabled
@bpy.app.handlers.persistent
def cleanup_on_load_pre(*args):
    """Handler that runs before a new .blend file is loaded to clean up temporary textures"""
    MaterialFactory.cleanup_flipped_textures()


def register():
    """Register the importer operator and menu function"""
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_importer)

    # Register the cleanup handler
    if cleanup_on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(cleanup_on_load_pre)


def unregister():
    """Unregister the importer operator and menu function"""
    bpy.utils.unregister_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_importer)

    # Unregister the cleanup handler
    if cleanup_on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cleanup_on_load_pre)

    # Clean up any remaining textures
    MaterialFactory.cleanup_flipped_textures()