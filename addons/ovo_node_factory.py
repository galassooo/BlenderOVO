# ================================================================
#  NODE FACTORY
# ================================================================
# This module defines the NodeFactory class responsible for creating
# generic Empty nodes in Blender for NodeRecord data that are not meshes or lights.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy

try:
    from .ovo_log import log
except ImportError:
    from ovo_log import log

# --------------------------------------------------------
# Node Factory
# --------------------------------------------------------
class NodeFactory:
    """
    NodeFactory creates a Blender Empty object for a generic node (NODE type).

    It sets up the display type and size of the empty to represent a node in the scene.
    """

    @staticmethod
    def create(rec):
        """
        Creates a Blender Empty object to represent a generic scene node.

        Args:
            rec (NodeRecord): Parsed node information from the OVO file.

        Returns:
            bpy.types.Object: Blender object representing the empty node.
        """
        node_obj = bpy.data.objects.new(rec.name, None)
        node_obj.empty_display_type = 'PLAIN_AXES'
        node_obj.empty_display_size = 1.0

        if not node_obj.users_collection:
            bpy.context.collection.objects.link(node_obj)

        log(f"Created empty node: '{rec.name}'", category="NODE", indent=1)
        return node_obj
