# ================================================================
#  MATERIAL FACTORY
# ================================================================
# This module defines the MaterialFactory class, responsible for
# converting an OVOMaterial data object into a properly configured
# Blender Material with nodes, textures, and proper linking.
# ================================================================

import os
import bpy

from .ovo_importer_utils import create_flipped_image


class MaterialFactory:
    """
    MaterialFactory converts an OVOMaterial data object into a Blender Material.

    It creates a new material, enables node usage, configures the Principled BSDF,
    loads texture images from disk, and sets up the appropriate node connections.
    """

    @staticmethod
    def create(ovo_material, texture_directory):
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
            if tex_file and tex_file != "[none]":
                tex_path = os.path.join(texture_directory, tex_file)
                if os.path.isfile(tex_path):
                    try:
                        # Load the image.
                        img = bpy.data.images.load(tex_path)
                        # Create a flipped copy of the image.
                        flipped_img = create_flipped_image(img)
                        tex_node = nodes.new('ShaderNodeTexImage')
                        tex_node.image = flipped_img
                        tex_node.label = node_label if node_label else f"{tex_key.capitalize()} Texture"
                        if set_non_color:
                            tex_node.image.colorspace_settings.name = 'Non-Color'
                        links.new(tex_node.outputs["Color"], bsdf.inputs[bsdf_input])
                    except Exception as ex:
                        print(f"[MaterialFactory] Error loading {tex_key} texture '{tex_path}': {ex}")
                else:
                    print(
                        f"[MaterialFactory] {tex_key.capitalize()} texture '{tex_file}' not found in {texture_directory}")

        # --- Albedo Map ---
        load_and_link("albedo", "Base Color", set_non_color=False, node_label="Albedo Texture")

        # --- Normal Map ---
        normal_file = ovo_material.textures.get("normal")
        if normal_file and normal_file != "[none]":
            normal_path = os.path.join(texture_directory, normal_file)
            if os.path.isfile(normal_path):
                try:
                    normal_img = bpy.data.images.load(normal_path)
                    # For normal maps we might not flip the image if the flipped result
                    # would break the conversion node. If needed, you could flip if your engine
                    # exports normal maps flipped.
                    # Optionally, apply the create_flipped_image function here as well.
                    normal_tex_node = nodes.new('ShaderNodeTexImage')
                    normal_tex_node.image = normal_img  # or flipped copy if appropriate
                    normal_tex_node.label = "Normal Map"
                    normal_tex_node.image.colorspace_settings.name = 'Non-Color'
                    normal_map_node = nodes.new('ShaderNodeNormalMap')
                    normal_map_node.label = "Normal Map Converter"
                    links.new(normal_tex_node.outputs["Color"], normal_map_node.inputs["Color"])
                    links.new(normal_map_node.outputs["Normal"], bsdf.inputs["Normal"])
                except Exception as ex:
                    print(f"[MaterialFactory] Error loading normal texture '{normal_path}': {ex}")
            else:
                print(f"[MaterialFactory] Normal texture '{normal_file}' not found in {texture_directory}")

        # --- Roughness Map ---
        load_and_link("roughness", "Roughness")

        # --- Metallic Map ---
        load_and_link("metalness", "Metallic")

        ovo_material.blender_material = mat
        return mat