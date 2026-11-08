"""ChatlogWidget: state of the header button that opens the image viewer."""

from components.button import set_visual_active
from components.image_viewer.gallery import first_image


class ChatlogImagesMixin:
    """ChatlogWidget: state of the header button that opens the image viewer."""

    def update_image_button(self):
        """Dim the images button while the shown messages hold no image."""
        set_visual_active(self.image_button, first_image(self.model.stored_messages) is not None)
