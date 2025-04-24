# ================================================================
#  MATERIAL FACTORY
# ================================================================
# This module defines the MaterialFactory class, responsible for
# converting an OVOMaterial data object into a properly configured
# Blender Material with nodes, textures, and proper linking.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import os
import bpy

try:
    from .ovo_texture_flipper import OVOTextureFlipper
    from .ovo_log import log
except ImportError:
    from ovo_texture_flipper import OVOTextureFlipper
    from ovo_log import log

# --------------------------------------------------------
# Material Factory
# --------------------------------------------------------
class MaterialFactory:
    """
    MaterialFactory converts an OVOMaterial data object into a Blender Material.

    It creates a new material, enables node usage, configures the Principled BSDF,
    loads texture images from disk, and sets up the appropriate node connections.
    """

    # Class-level storage for tracking flipped texture files
    # We need to keep these files as long as Blender is using them
    flipped_textures = set()

    @staticmethod
    def create(ovo_material, texture_directory, flip_textures=True):
        mat = bpy.data.materials.new(name=ovo_material.name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Locate the Principled BSDF node.
        bsdf = None
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if bsdf is None:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')

        # Set basic material properties.
        bsdf.inputs["Base Color"].default_value = (*ovo_material.base_color, 1.0)
        bsdf.inputs["Roughness"].default_value = ovo_material.roughness
        bsdf.inputs["Metallic"].default_value = ovo_material.metallic
        if ovo_material.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = ovo_material.transparency
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*ovo_material.emissive, 1.0)

        def load_and_link(tex_key, bsdf_input, set_non_color=True, node_label=""):
            tex_file = ovo_material.textures.get(tex_key)
            if not tex_file or tex_file == "[none]":
                log(f"No {tex_key} texture defined for material '{ovo_material.name}'", category="MATERIAL", indent=1)
                return

            tex_path = os.path.join(texture_directory, tex_file)
            if not os.path.isfile(tex_path):
                log(f"{tex_key.capitalize()} texture '{tex_file}' not found at '{tex_path}'", category="WARNING", indent=1)
                return

            # Flag to track if we've created a flipped version
            flipped_version_created = False
            original_path = tex_path

            try:
                # Check if it's a DDS file that needs flipping
                if flip_textures and tex_path.lower().endswith('.dds'):
                    if OVOTextureFlipper.is_dds_file(tex_path):
                        # Create a flipped file with a distinctive name
                        texture_name = os.path.basename(tex_path)
                        texture_base, texture_ext = os.path.splitext(texture_name)
                        flipped_path = os.path.join(texture_directory, f"{texture_base}_flipped{texture_ext}")

                        log(f"[MaterialFactory] Flipping {tex_key} texture '{tex_file}'", category="MATERIAL", indent=1)
                        try:
                            OVOTextureFlipper.flip_dds_texture(tex_path, flipped_path)
                            tex_path = flipped_path  # Use the flipped texture
                            flipped_version_created = True
                            # Add to our tracking set so we know this is a flipped texture
                            MaterialFactory.flipped_textures.add(flipped_path)

                            log(f"[MaterialFactory] Texture flipped successfully: '{flipped_path}'", category="MATERIAL", indent=2)
                        except Exception as ex:
                            log(f"[MaterialFactory] Failed to flip texture: {ex}", category="ERROR", indent=2)
                            log("[MaterialFactory] Using original texture instead", category="WARNING", indent=2)
                            tex_path = original_path

                # Try to load the image
                log(f"[MaterialFactory] Loading texture from: '{tex_path}'", category="MATERIAL", indent=2)
                img = bpy.data.images.load(tex_path, check_existing=True)
                log(f"[MaterialFactory] Texture loaded successfully: '{img.name}'", category="MATERIAL", indent=2)

                # Create and configure the texture node
                tex_node = nodes.new('ShaderNodeTexImage')
                tex_node.image = img
                tex_node.label = node_label if node_label else f"{tex_key.capitalize()} Texture"
                if set_non_color:
                    tex_node.image.colorspace_settings.name = 'Non-Color'

                # Connect the texture to the shader
                links.new(tex_node.outputs["Color"], bsdf.inputs[bsdf_input])
                log(f"[MaterialFactory] Connected '{tex_node.label}' to '{bsdf_input}'", category="MATERIAL", indent=2)

            except Exception as ex:
                log(f"[MaterialFactory] Error processing {tex_key} texture '{tex_path}': {ex}", category="ERROR", indent=2)

                # If we created a flipped version but failed to use it, we can clean it up
                if flipped_version_created and not os.path.samefile(tex_path, flipped_path):
                    try:
                        os.remove(flipped_path)
                        MaterialFactory.flipped_textures.discard(flipped_path)
                        log(f"[MaterialFactory] Removed unused flipped texture: '{flipped_path}'", category="MATERIAL", indent=2)
                    except:
                        pass

        # --- Load and assign maps ---

        # --- Albedo Map ---
        load_and_link("albedo", "Base Color", set_non_color=False, node_label="Albedo Texture")

        # --- Normal Map ---
        normal_file = ovo_material.textures.get("normal")
        if normal_file and normal_file != "[none]":
            normal_path = os.path.join(texture_directory, normal_file)
            if not os.path.isfile(normal_path):
                log(f"[MaterialFactory] Normal texture '{normal_file}' not found at '{normal_path}'", category="WARNING", indent=1)
            else:
                # Flag to track if we've created a flipped version
                flipped_version_created = False
                original_path = normal_path

                try:
                    # Check if it's a DDS file that needs flipping
                    if flip_textures and normal_path.lower().endswith('.dds'):
                        if OVOTextureFlipper.is_dds_file(normal_path):
                            # Create a flipped file with a distinctive name
                            texture_name = os.path.basename(normal_path)
                            texture_base, texture_ext = os.path.splitext(texture_name)
                            flipped_path = os.path.join(texture_directory, f"{texture_base}_flipped{texture_ext}")

                            log(f"[MaterialFactory] Flipping normal map '{normal_file}'", category="MATERIAL", indent=1)
                            try:
                                OVOTextureFlipper.flip_dds_texture(normal_path, flipped_path)
                                normal_path = flipped_path  # Use the flipped texture
                                flipped_version_created = True
                                # Add to our tracking set
                                MaterialFactory.flipped_textures.add(flipped_path)
                                log(f"[MaterialFactory] Normal map flipped: '{flipped_path}'", category="MATERIAL", indent=2)
                            except Exception as ex:
                                log(f"[MaterialFactory] Failed to flip normal map: {ex}", category="ERROR", indent=2)
                                log("[MaterialFactory] Using original normal map instead", category="WARNING", indent=2)
                                normal_path = original_path

                    # Try to load the normal map

                    log(f"[MaterialFactory] Loading normal map: '{normal_path}'", category="MATERIAL", indent=2)
                    normal_img = bpy.data.images.load(normal_path, check_existing=True)
                    log(f"[MaterialFactory] Normal map loaded: '{normal_img.name}'", category="MATERIAL", indent=2)

                    # Create the texture node for the normal map
                    normal_tex_node = nodes.new('ShaderNodeTexImage')
                    normal_tex_node.image = normal_img
                    normal_tex_node.label = "Normal Map"
                    normal_tex_node.image.colorspace_settings.name = 'Non-Color'

                    # Add normal map converter node
                    normal_map_node = nodes.new('ShaderNodeNormalMap')
                    normal_map_node.label = "Normal Map Converter"

                    # Connect the nodes
                    links.new(normal_tex_node.outputs["Color"], normal_map_node.inputs["Color"])
                    links.new(normal_map_node.outputs["Normal"], bsdf.inputs["Normal"])
                    log("[MaterialFactory] Normal map node setup complete", category="MATERIAL", indent=2)

                except Exception as ex:
                    log(f"[MaterialFactory] Error processing normal map: {ex}", category="ERROR", indent=2)
                    # If we created a flipped version but failed to use it, we can clean it up
                    if flipped_version_created and not os.path.samefile(normal_path, flipped_path):
                        try:
                            os.remove(flipped_path)
                            MaterialFactory.flipped_textures.discard(flipped_path)
                            log(f"[MaterialFactory] Removed unused flipped texture: '{flipped_path}'", category="MATERIAL", indent=2)
                        except:
                            pass

        # --- Roughness Map ---
        load_and_link("roughness", "Roughness")

        # --- Metallic Map ---
        load_and_link("metalness", "Metallic")

        ovo_material.blender_material = mat
        return mat

    @staticmethod
    def cleanup_flipped_textures():
        """
        Clean up any flipped textures created during the import process.
        This should be called when the addon is being unregistered or when Blender is closing.
        """
        textures_to_remove = list(MaterialFactory.flipped_textures)
        for tex_path in textures_to_remove:
            try:
                # Check if Blender is still using this texture
                tex_name = os.path.basename(tex_path)
                if tex_name in bpy.data.images:
                    # If it's still in use, don't delete it yet
                    log(f"[MaterialFactory] Texture '{tex_name}' still in use, not deleting", category="MATERIAL", indent=1)
                    continue

                if os.path.exists(tex_path):
                    os.remove(tex_path)
                    log(f"[MaterialFactory] Removed flipped texture: '{tex_path}'", category="MATERIAL", indent=1)
                MaterialFactory.flipped_textures.remove(tex_path)
            except Exception as ex:
                log(f"[MaterialFactory] Error removing flipped texture '{tex_path}': {ex}", category="ERROR", indent=1)