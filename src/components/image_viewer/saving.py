"""Saving the shown image to a file chosen by the user."""

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImageReader
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from components.image_viewer.gallery import IMAGE_SUFFIXES
from helpers.data import get_data_dir
from helpers.translate import tr


_DEFAULT_FILE_NAME = "image"


def _file_name(url: str, data: bytes) -> str:
    """File name from the url, with the extension taken from the data when the url has none."""
    name = unquote(PurePosixPath(urlparse(url).path).name) or _DEFAULT_FILE_NAME
    if PurePosixPath(name).suffix.lstrip(".").lower() in IMAGE_SUFFIXES:
        return name
    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    image_format = bytes(QImageReader.imageFormat(buffer)).decode()
    return f"{name}.{image_format}" if image_format else name


def save_image(parent: QWidget, url: str, data: bytes):
    """Ask where to save the image and write its bytes there; the user is told when writing fails."""
    suffix_filter = " ".join(f"*.{suffix}" for suffix in IMAGE_SUFFIXES)
    file_filter = f"{tr('Images', 'Изображения')} ({suffix_filter});;{tr('All Files', 'Все файлы')} (*)"
    path, _ = QFileDialog.getSaveFileName(
        parent, tr("Save image", "Сохранить изображение"), str(get_data_dir("images") / _file_name(url, data)), file_filter
    )
    if not path:
        return
    try:
        Path(path).write_bytes(data)
    except OSError as error:
        QMessageBox.critical(
            parent, tr("Error", "Ошибка"), tr(f"Failed to save file:\n{error}", f"Не удалось сохранить файл:\n{error}")
        )
