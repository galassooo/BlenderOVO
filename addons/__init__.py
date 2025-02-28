bl_info = {
    "name": "OVO Exporter",
    "author": "Martina Galasso",
    "version": (0, 1),
    "blender": (4, 2, 1),
    "location": "File > Export > OverView Object (.ovo)",
    "description": "Export the current scene to the OVO file format",
    "category": "Import-Export",
}

from .exportOvo import register, unregister

if __name__ == "__main__":
    register()
