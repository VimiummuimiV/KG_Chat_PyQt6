"""Star mark appended to the username of a tracked user."""

_TRACKED_MARK = " ⭐"


class TrackedMarkMixin:
    """Adds set_tracked() to a user row that has is_tracked and username_label."""

    def set_tracked(self, tracked: bool):
        """Show or hide the tracked star next to the username."""
        if tracked == self.is_tracked:
            return
        self.is_tracked = tracked
        text = self.username_label.text()
        self.username_label.setText(text + _TRACKED_MARK if tracked else text.replace(_TRACKED_MARK, ""))
