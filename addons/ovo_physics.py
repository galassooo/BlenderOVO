"""
ovo_physics.py
Manages physics for OVO export.
This module handles extracting and serializing physics properties from Blender objects.
"""

import struct
import mathutils

try:
    # When executed as addon
    from .ovo_types import HullType
    from .ovo_packer import OVOPacker
except ImportError:
    # When executed directly
    from ovo_types import HullType
    from ovo_packer import OVOPacker


class OVOPhysicsManager:
    """
    Manages physics properties of objects for OVO export.
    """

    def __init__(self, packer):
        """
        Initializes the physics manager.

        Args:
            packer (OVOPacker): Instance of the packer to serialize data
        """
        self.packer = packer

    def has_physics(self, obj):
        """
        Checks if an object has physics properties.

        Args:
            obj: Blender object to check

        Returns:
            bool: True if the object has physics properties, False otherwise
        """
        return obj.rigid_body is not None

    def get_physics_type(self, obj):
        """
        Gets the physics type of the object.

        Args:
            obj: Blender object with physics properties

        Returns:
            int: 0 for static objects, 1 for dynamic objects
        """
        if not self.has_physics(obj):
            return 0

        if obj.rigid_body.type == 'ACTIVE':
            return 1  # Dynamic
        else:
            return 0  # Static (default)

    def get_hull_type(self, obj):
        """
        Gets the hull collision type of the object.

        Args:
            obj: Blender object with physics properties

        Returns:
            int: Hull collision type defined in HullType
        """
        if not self.has_physics(obj):
            return HullType.HULL_BOX  # Default

        # Collision shape type
        hull_type = HullType.HULL_BOX  # Default is box (2)

        if hasattr(obj.rigid_body, 'collision_shape'):
            if obj.rigid_body.collision_shape == 'SPHERE':
                hull_type = HullType.HULL_SPHERE  # 1
            elif obj.rigid_body.collision_shape == 'BOX':
                hull_type = HullType.HULL_BOX  # 2
            elif obj.rigid_body.collision_shape == 'CAPSULE':
                hull_type = HullType.HULL_CAPSULE  # 3
            elif obj.rigid_body.collision_shape == 'CONVEX_HULL':
                hull_type = HullType.HULL_CONVEX  # 4
            elif obj.rigid_body.collision_shape == 'MESH':
                hull_type = HullType.HULL_CONCAVE  # 7

        return hull_type

    def get_mass_center(self, obj):
        """
        Calculates the center of mass of the object.

        Args:
            obj: Blender object

        Returns:
            mathutils.Vector: Coordinates of the center of mass
        """
        # Calculate mesh center using bounding box
        local_bbox_center = sum((mathutils.Vector(b) for b in obj.bound_box), mathutils.Vector()) / 8
        return local_bbox_center

    def write_physics_data(self, obj, chunk_data):
        """
        Writes physics data to the chunk.

        Args:
            obj: Blender object with physics properties
            chunk_data: Binary buffer of the chunk

        Returns:
            bytes: Updated binary buffer with physics data
        """
        # Physics presence flag
        has_physics = self.has_physics(obj)
        chunk_data += struct.pack('B', 1 if has_physics else 0)

        # If the object has no physics properties, end here
        if not has_physics:
            print(f"    [OVOPhysicsManager] Object '{obj.name}' has no physics properties")
            return chunk_data

        # Physics type
        physics_type = self.get_physics_type(obj)

        # Other physics properties
        cont_collision = 1  # Default active
        collide_with_rbodies = 1 if obj.rigid_body.enabled else 0
        hull_type = self.get_hull_type(obj)

        # Map hull type to string name for debug
        hull_names = {
            HullType.HULL_UNDEFINED: "UNDEFINED",
            HullType.HULL_SPHERE: "SPHERE",
            HullType.HULL_BOX: "BOX",
            HullType.HULL_CAPSULE: "CAPSULE",
            HullType.HULL_CONVEX: "CONVEX",
            HullType.HULL_ORIGINAL: "ORIGINAL",
            HullType.HULL_CUSTOM: "CUSTOM",
            HullType.HULL_CONCAVE: "CONCAVE"
        }
        hull_name = hull_names.get(hull_type, "UNKNOWN")

        print(f"    [OVOPhysicsManager] Object '{obj.name}' physics properties:")
        print(f"      - Type: {'DYNAMIC' if physics_type == 1 else 'STATIC'}")
        print(f"      - Hull: {hull_name} (code: {hull_type})")
        print(f"      - Active: {obj.rigid_body.enabled}")

        # Pack control bytes
        chunk_data += struct.pack('B', physics_type)
        chunk_data += struct.pack('B', cont_collision)
        chunk_data += struct.pack('B', collide_with_rbodies)
        chunk_data += struct.pack('B', hull_type)

        # Center of mass
        mass_center = self.get_mass_center(obj)
        chunk_data += self.packer.pack_vector3(mass_center)
        print(f"      - Mass center: ({mass_center.x:.3f}, {mass_center.y:.3f}, {mass_center.z:.3f})")

        # Physics properties - use safe getters to avoid AttributeError
        mass = getattr(obj.rigid_body, 'mass', 1.0)
        static_friction = getattr(obj.rigid_body, 'friction', 0.5)
        dynamic_friction = static_friction  # Use the same value
        bounciness = getattr(obj.rigid_body, 'restitution', 0.0)
        linear_damping = getattr(obj.rigid_body, 'linear_damping', 0.04)
        angular_damping = getattr(obj.rigid_body, 'angular_damping', 0.1)

        print(f"      - Mass: {mass:.2f}")
        print(f"      - Friction: {static_friction:.2f}")
        print(f"      - Bounciness: {bounciness:.2f}")
        print(f"      - Damping: linear={linear_damping:.2f}, angular={angular_damping:.2f}")

        # Write values
        chunk_data += struct.pack('f', mass)
        chunk_data += struct.pack('f', static_friction)
        chunk_data += struct.pack('f', dynamic_friction)
        chunk_data += struct.pack('f', bounciness)
        chunk_data += struct.pack('f', linear_damping)
        chunk_data += struct.pack('f', angular_damping)

        # We don't export custom hulls for now
        nr_of_hulls = 0
        chunk_data += struct.pack('I', nr_of_hulls)
        chunk_data += struct.pack('I', 0)  # Padding

        # Pointers (set to zero in the file)
        chunk_data += struct.pack('Q', 0)  # physObj pointer
        chunk_data += struct.pack('Q', 0)  # hull pointer

        print(f"    [OVOPhysicsManager] Physics data written for '{obj.name}'")
        return chunk_data