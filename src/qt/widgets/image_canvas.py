import time

from PIL import Image

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH, BORDER_THICKNESS
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QColor,
        QGraphicsItem,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
        QPainter,
        QPen,
        QPixmap,
        QTransform,
        Qt,
        Signal,
    )


from src.qt.pixmap_utils import pil_to_qpixmap as _pil_to_qpixmap


if QT_AVAILABLE:
    class _DraggablePixmapItem(QGraphicsPixmapItem):
        def __init__(self, on_change=None, on_interaction_start=None):
            super().__init__()
            self._on_change = on_change
            self._on_interaction_start = on_interaction_start
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        def mousePressEvent(self, event):
            if self._on_interaction_start:
                self._on_interaction_start()
            super().mousePressEvent(event)

        def itemChange(self, change, value):
            if change == QGraphicsItem.ItemPositionHasChanged and self._on_change:
                self._on_change()
            return super().itemChange(change, value)


    class ImageCanvas(QGraphicsView):
        state_changed = Signal(tuple, tuple)
        border_pos_changed = Signal(tuple)
        interaction_started = Signal()
        color_picked = Signal(str)
        zoom_changed = Signal(float)  # B4: emits zoom factor (1.0 = original size)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setRenderHint(QPainter.Antialiasing)
            self.setRenderHint(QPainter.SmoothPixmapTransform)
            self.setBackgroundBrush(QColor("#141821"))
            self.setFrameShape(QGraphicsView.NoFrame)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

            self.scene = QGraphicsScene(self)
            self.setScene(self.scene)
            self.scene.setSceneRect(0, 0, 1400, 900)

            self.border_item = QGraphicsRectItem()
            self.border_item.setZValue(10)
            self.scene.addItem(self.border_item)
            self.preview_item = QGraphicsPixmapItem()
            self.preview_item.setZValue(12)
            self.preview_item.setVisible(False)
            self.scene.addItem(self.preview_item)
            self.image_item = None
            self._base_image = None
            self._base_pixmap = None
            self._current_size = None
            self._border_pos = (0, 0)
            self._border_color = "#FFFFFF"
            self._color_pick_enabled = False
            self._zoom_factor = 1.0  # B4
            self._last_wheel_time = 0.0  # F8: debounce do snapshot de undo
            # C2: before/after toggle state
            self._before_after_active = False
            self._original_image = None
            self._saved_edit_pos = None
            self._saved_edit_size = None
            self._layout_border(initial=True)

        @property
        def border_pos(self):
            return self._border_pos

        def _layout_border(self, initial=False):
            old_pos = self._border_pos
            viewport_rect = self.viewport().rect()
            width = max(viewport_rect.width(), BORDA_WIDTH + 100)
            height = max(viewport_rect.height(), BORDA_HEIGHT + 100)
            self.scene.setSceneRect(0, 0, width, height)

            bx = int((width - BORDA_WIDTH) / 2)
            by = int((height - BORDA_HEIGHT) / 2)
            self._border_pos = (bx, by)
            self.border_item.setRect(bx, by, BORDA_WIDTH, BORDA_HEIGHT)
            self.border_item.setPen(QPen(QColor(self._border_color), BORDER_THICKNESS))
            self.preview_item.setPos(bx, by)
            self.border_pos_changed.emit(self._border_pos)

            if not initial and self.image_item is not None:
                delta_x = bx - old_pos[0]
                delta_y = by - old_pos[1]
                self.image_item.setPos(self.image_item.pos().x() + delta_x, self.image_item.pos().y() + delta_y)
                self._emit_state_changed()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._layout_border()

        def clear_image(self):
            if self.image_item is not None:
                self.scene.removeItem(self.image_item)
                self.image_item = None
            self._base_image = None
            self._base_pixmap = None
            self._current_size = None
            self._original_image = None
            self._before_after_active = False
            self._saved_edit_pos = None
            self._saved_edit_size = None

        def set_border_color(self, color_hex):
            self._border_color = color_hex
            self.border_item.setPen(QPen(QColor(color_hex), BORDER_THICKNESS))

        def set_color_pick_enabled(self, enabled):
            self._color_pick_enabled = bool(enabled)
            self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

        def set_preview_overlay(self, pixmap):
            if pixmap is None or pixmap.isNull():
                self.clear_preview_overlay()
                return
            self.preview_item.setPixmap(pixmap)
            self.preview_item.setPos(*self._border_pos)
            self.preview_item.setVisible(True)
            self.border_item.setVisible(False)

        def clear_preview_overlay(self):
            self.preview_item.setPixmap(QPixmap())
            self.preview_item.setVisible(False)
            self.border_item.setVisible(True)

        def _apply_size_transform(self, size):
            if self.image_item is None or self._base_pixmap is None:
                return
            width = max(1, int(size[0]))
            height = max(1, int(size[1]))
            base_width = max(1, self._base_pixmap.width())
            base_height = max(1, self._base_pixmap.height())
            transform = QTransform.fromScale(width / base_width, height / base_height)
            self.image_item.setTransform(transform)
            self._current_size = (width, height)
            # B4: derive and emit zoom factor relative to natural image size
            self._zoom_factor = width / max(1, self._base_image.width) if self._base_image else 1.0

        def set_image(self, pil_image, state=None, border_color="#FFFFFF"):
            self.clear_image()
            self._base_image = pil_image.convert("RGBA")
            self._original_image = self._base_image.copy()  # C2: keep original
            self._base_pixmap = _pil_to_qpixmap(self._base_image)
            self.set_border_color(border_color)

            pos = state["pos"] if state else self._border_pos
            size = state["size"] if state else self._base_image.size
            self.image_item = _DraggablePixmapItem(
                on_change=self._emit_state_changed,
                on_interaction_start=self.interaction_started.emit,
            )
            self.image_item.setZValue(1)
            self.image_item.setTransformationMode(Qt.SmoothTransformation)
            self.image_item.setPixmap(self._base_pixmap)
            self.image_item.setPos(*pos)
            self.scene.addItem(self.image_item)
            self._apply_size_transform(size)
            self._emit_state_changed()

        def set_image_state(self, pos, size):
            if self.image_item is None or self._base_image is None:
                return
            self.image_item.setPos(*pos)
            self._apply_size_transform(size)
            self._emit_state_changed()

        # ── C2: before/after toggle ────────────────────────────────────────

        def show_original_preview(self):
            """C2: temporarily show the original unedited image filling the border."""
            if self._original_image is None or self.image_item is None:
                return
            if self._before_after_active:
                return
            # save the edit placement BEFORE moving anything, and raise the flag
            # first so the temporary reposition never reaches state_changed
            self._saved_edit_pos = (self.image_item.pos().x(), self.image_item.pos().y())
            self._saved_edit_size = self._current_size
            self._before_after_active = True
            orig_pixmap = _pil_to_qpixmap(self._original_image)
            # fit the original inside the border box
            bx, by = self._border_pos
            self.image_item.setPixmap(orig_pixmap)
            self.image_item.resetTransform()
            scale_x = BORDA_WIDTH / max(1, orig_pixmap.width())
            scale_y = BORDA_HEIGHT / max(1, orig_pixmap.height())
            scale = min(scale_x, scale_y)
            transform = QTransform.fromScale(scale, scale)
            self.image_item.setTransform(transform)
            self.image_item.setPos(bx, by)
            self.border_item.setVisible(False)
            self.preview_item.setVisible(False)

        def restore_edit_preview(self):
            """C2: restore the edited state after before/after toggle."""
            if not self._before_after_active or self._base_image is None:
                return
            self.image_item.setPixmap(self._base_pixmap)
            if self._saved_edit_size is not None:
                self._apply_size_transform(self._saved_edit_size)
            if self._saved_edit_pos is not None:
                self.image_item.setPos(*self._saved_edit_pos)
            # only lower the flag after the placement is back, so the restore
            # repositioning is also suppressed from state_changed
            self._before_after_active = False
            self._saved_edit_pos = None
            self._saved_edit_size = None
            self.border_item.setVisible(True)

        # ── B4: zoom via wheel ─────────────────────────────────────────────

        def wheelEvent(self, event):
            if self.image_item is None or self._base_image is None:
                super().wheelEvent(event)
                return

            # F8: uma sequência de ticks é um único gesto — só cria snapshot de
            # undo se o último tick foi há mais de 0,5s
            now = time.monotonic()
            if now - self._last_wheel_time > 0.5:
                self.interaction_started.emit()
            self._last_wheel_time = now
            delta = event.angleDelta().y()
            factor = 1.05 if delta > 0 else 0.95
            width = max(1, int(self._current_size[0] * factor))
            height = max(1, int(self._current_size[1] * factor))
            self.set_image_state(
                (int(self.image_item.pos().x()), int(self.image_item.pos().y())),
                (width, height),
            )
            self.zoom_changed.emit(self._zoom_factor)  # B4
            event.accept()

        def keyPressEvent(self, event):
            # deixa ←/→ subirem até a janela para navegar entre imagens (F3)
            if event.key() in (Qt.Key_Left, Qt.Key_Right) and event.modifiers() == Qt.NoModifier:
                event.ignore()
                return
            super().keyPressEvent(event)

        def mousePressEvent(self, event):
            if self._color_pick_enabled and self.image_item is not None and self._base_image is not None:
                scene_pos = self.mapToScene(event.position().toPoint())
                local_pos = self.image_item.mapFromScene(scene_pos)
                x = int(local_pos.x())
                y = int(local_pos.y())
                if 0 <= x < self._base_image.width and 0 <= y < self._base_image.height:
                    try:
                        pixel = self._base_image.getpixel((x, y))
                        if isinstance(pixel, int):
                            color = "#{0:02x}{0:02x}{0:02x}".format(pixel)
                        else:
                            r, g, b = pixel[:3]
                            color = f"#{r:02x}{g:02x}{b:02x}"
                        self.color_picked.emit(color)
                    except Exception:
                        pass
                    event.accept()
                    return
            super().mousePressEvent(event)

        def _emit_state_changed(self):
            if self.image_item is None or self._current_size is None:
                return
            if self._before_after_active:
                return
            pos = (int(self.image_item.pos().x()), int(self.image_item.pos().y()))
            self.state_changed.emit(pos, self._current_size)
            self.zoom_changed.emit(self._zoom_factor)  # B4: emit on any state change too
else:
    class ImageCanvas:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
