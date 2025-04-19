# ================================================================
# OVO TOOLS - BLENDER ADDON
# ================================================================
# Entry point for the OVO Tools addon.
# Registers all import/export UI panels and operators,
# manages cleanup handlers, and integrates with Blender menus.
# ================================================================

bl_info = {
    "name": "OVO Tools (Importer & Exporter)",
    "author": "Kevin Quarenghi & Martina Galasso",
    "version": (1, 0),
    "blender": (4, 2, 1),
    "location": "File > Import/Export > OverView Object (.ovo)",
    "description": "Import & Export the current scene to the OVO file format",
    "category": "Import-Export",
}

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

import sys
import os

# Get the absolute path of the directory containing this file
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --------------------------------------------------------
# ADD-ON MODULES IMPORTS (EXPORTER)
# --------------------------------------------------------
from .ovo_exporter_ui import register as exporter_register, unregister as exporter_unregister

# --------------------------------------------------------
# IMPORTER IMPORTS
# --------------------------------------------------------
from .ovo_importer_ui import register as importer_register, unregister as importer_unregister

# --------------------------------------------------------
# CLEANUP HANDLER
# --------------------------------------------------------
from .ovo_material_factory import MaterialFactory

@bpy.app.handlers.persistent
def cleanup_on_exit(*args):
    """Handler che viene eseguito quando Blender sta per chiudersi"""
    print("[OVO Tools] Cleaning up temporary files")
    MaterialFactory.cleanup_flipped_textures()

# --------------------------------------------------------
# REGISTER / UNREGISTER
# --------------------------------------------------------
def register():
    """Register exporter, importer, and cleanup handlers."""
    # === Exporter Registration ===
    exporter_register()

    # === Importer Registration ===
    importer_register()

    # === Cleanup Registration ===
    if cleanup_on_exit not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(cleanup_on_exit)
    if cleanup_on_exit not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(cleanup_on_exit)


def unregister():
    """Unregister cleanup handlers, importer, and exporter."""
    # === Run Cleanup ===
    cleanup_on_exit()

    # === Cleanup Unregister ===
    if cleanup_on_exit in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cleanup_on_exit)
    if cleanup_on_exit in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(cleanup_on_exit)

    # === Exporter Unregister ===
    exporter_unregister()

    # === Importer Unregister ===
    importer_unregister()

# --------------------------------------------------------
# Dev Main
# --------------------------------------------------------
if __name__ == "__main__":
    register()
    print("Addon OVO registerd.")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))

        blend_path = os.path.join(script_dir, "../scenes", "scarpa2.blend")

        bpy.ops.wm.open_mainfile(filepath=blend_path)
        print(f"Uploaded scene from: {blend_path}")

        output_path = os.path.join(script_dir, "../bin", "output.ovo")

        bpy.ops.export_scene.ovo(
            filepath=output_path,
            use_mesh=True,
            use_light=True,
            use_legacy_compression=True
        )
        print(f"Export Completed, file saved in: {output_path}")

    except Exception as e:
        print(f"Error during export: {e}")
        import traceback
        traceback.print_exc()

    unregister()
    print("OVO addon unregister.")