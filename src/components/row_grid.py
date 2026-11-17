"""Grid placement of equally sized rows: as many columns as fit the width."""

from PyQt6.QtWidgets import QGridLayout, QWidget


def fill_grid(grid: QGridLayout, widgets: list[QWidget], available_width: int) -> None:
    """Put the widgets into the grid in reading order; a widget already in its place is not touched."""
    if not widgets:
        return
    spacing = grid.horizontalSpacing()
    if spacing == -1:
        spacing = grid.spacing()
    margins = grid.contentsMargins()
    usable_width = available_width - margins.left() - margins.right()
    columns = max(1, (usable_width + spacing) // (max(widget.width() for widget in widgets) + spacing))
    for index, widget in enumerate(widgets):
        position = (index // columns, index % columns)
        grid_index = grid.indexOf(widget)
        if grid_index >= 0:
            if grid.getItemPosition(grid_index)[:2] == position:
                continue
            grid.removeWidget(widget)
        grid.addWidget(widget, *position)
