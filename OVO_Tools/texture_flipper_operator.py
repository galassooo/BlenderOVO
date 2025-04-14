import bpy
import numpy as np
from bpy.props import IntProperty

def create_flipped_image(image):
    """
    Create and return a flipped copy of the given image.
    The copy will contain the vertically flipped pixel data.

    :param image: The original bpy.types.Image instance.
    :return: A new bpy.types.Image instance with pixels flipped vertically.
    """
    try:
        width, height = image.size
        channels = image.channels  # Use the actual channel count (commonly 4 for RGBA)
        total = width * height * channels

        # Create a Python list and retrieve pixels using foreach_get
        pixels = [0.0] * total
        image.pixels.foreach_get(pixels)

        # Convert to NumPy array and reshape to a 3D array (height, width, channels)
        arr = np.array(pixels, dtype=np.float32).reshape((height, width, channels))

        # Flip the array vertically
        arr = np.flipud(arr)

        # Create a new image to hold the flipped pixel data;
        new_image_name = image.name + "_flipped"
        new_image = bpy.data.images.new(new_image_name, width, height, alpha=(channels == 4))

        # Write the flipped pixel data back into the new image
        new_image.pixels.foreach_set(arr.flatten().tolist())
        new_image.update()

        new_image["flipped"] = True

        return new_image
    except Exception as e:
        print(f"[create_flipped_image] Error flipping image '{image.name}': {e}")
        return image


class TextureFlipperOperator(bpy.types.Operator):
    """Operator that processes a batch of textures to flip them vertically (in memory)."""
    bl_idname = "wm.texture_flipper"
    bl_label = "Flip Textures (Batch Processing)"

    batch_size: IntProperty(
        name="Batch Size",
        description="Number of textures to flip per iteration",
        default=1
    )

    _timer = None
    _textures = []
    _index = 0

    def execute(self, context):
        # If no textures to process, finish immediately.
        if not self._textures:
            self.report({'INFO'}, "No textures need flipping.")
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            for _ in range(self.batch_size):
                if self._index < len(self._textures):
                    orig_img = self._textures[self._index]

                    # 1) Creiamo un nuovo Image ribaltando i pixel di 'orig_img'
                    flipped_img = create_flipped_image(orig_img)

                    # 2) Assegniamo flipped_img ai nodi che prima usavano 'orig_img'
                    for mat in bpy.data.materials:
                        if mat.use_nodes:
                            for node in mat.node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and node.image == orig_img:
                                    node.image = flipped_img

                    self._index += 1

                else:
                    # Fine
                    self.report({'INFO'}, "Texture flipping completed.")
                    context.window_manager.event_timer_remove(self._timer)
                    return {'FINISHED'}

            # ridisegna la viewport
            for area in bpy.context.screen.areas:
                if area.type in {'VIEW_3D', 'IMAGE_EDITOR'}:
                    area.tag_redraw()

            self.report({'INFO'}, f"Flipped {self._index} textures out of {len(self._textures)}")

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        # Gather the list of textures that require flipping
        self._textures = [
            img for img in bpy.data.images
            if img.get("flip_required", False) and not img.get("flipped", False)
        ]
        self._index = 0

        wm = context.window_manager

        self._timer = wm.event_timer_add(time_step=1, window=context.window)
        wm.modal_handler_add(self)

        print("[TextureFlipper] Starting batch processing of textures.")
        return {'RUNNING_MODAL'}

def register():
    bpy.utils.register_class(TextureFlipperOperator)

def unregister():
    bpy.utils.unregister_class(TextureFlipperOperator)
