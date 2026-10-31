import time

from PIL import Image

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH, BORDER_THICKNESS
from src.core.image_processor import uncovered_regions
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QApplication,
        QBrush,
        QColor,
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
        QLabel,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
        QPointF,
        QTimer,
        QTransform,
        Qt,
        Signal,
    )


from src.qt.pixmap_utils import pil_to_qpixmap as _pil_to_qpixmap
from src.qt.theme import tokens as _theme_tokens


# M8: passo da roda — fino por padrão, rápido com Ctrl pressionado
ZOOM_STEP_FINE = 1.05
ZOOM_STEP_FAST = 1.2
# distância (px de tela = px de cena: o zoom muda o item, não a vista) em que
# a imagem arrastada gruda nas bordas/centro da custom
SNAP_THRESHOLD_PX = 8


def snap_offsets(image_rect, border_rect, threshold=SNAP_THRESHOLD_PX):
    """Deslocamento (dx, dy) que encaixa a imagem na borda, e se encaixou no centro.

    X: borda esquerda ↔ esquerda, direita ↔ direita, centro ↔ centro; Y: topo ↔
    topo, base ↔ base. Por eixo vale o candidato mais próximo dentro do limiar;
    com a imagem mais estreita que a borda, o centro tem preferência (as
    bordas não fazem sentido quando a imagem nem alcança as duas).
    """
    ix, iy, iw, ih = image_rect
    bx, by, bw, bh = border_rect

    def pick(candidates, prefer_center):
        inside = [(abs(d), d, kind) for d, kind in candidates if abs(d) <= threshold]
        if not inside:
            return 0, None
        if prefer_center:
            centered = [c for c in inside if c[2] == "center"]
            if centered:
                return centered[0][1], "center"
        best = min(inside)
        return best[1], best[2]

    dx, kind_x = pick(
        [(bx - ix, "left"), ((bx + bw) - (ix + iw), "right"), ((bx + bw / 2) - (ix + iw / 2), "center")],
        prefer_center=iw < bw,
    )
    dy, _kind_y = pick([(by - iy, "top"), ((by + bh) - (iy + ih), "bottom")], prefer_center=False)
    return dx, dy, kind_x == "center"


def scaled_placement(pos, size, factor, anchor):
    """Escala (pos, size) por `factor` mantendo o ponto `anchor` (coordenadas
    de cena) parado na tela — o mesmo comportamento de zoom de editores de imagem."""
    old_w, old_h = size
    new_w = max(1, int(round(old_w * factor)))
    new_h = max(1, int(round(old_h * factor)))
    ratio_x = new_w / max(1, old_w)
    ratio_y = new_h / max(1, old_h)
    ax, ay = anchor
    new_x = ax - (ax - pos[0]) * ratio_x
    new_y = ay - (ay - pos[1]) * ratio_y
    return (int(round(new_x)), int(round(new_y))), (new_w, new_h)


if QT_AVAILABLE:
    class _DraggablePixmapItem(QGraphicsPixmapItem):
        def __init__(self, on_change=None, on_interaction_start=None, snap_fn=None, on_drag=None):
            super().__init__()
            self._on_change = on_change
            self._on_interaction_start = on_interaction_start
            self._snap_fn = snap_fn  # QPointF -> QPointF, só durante o arrasto
            self._on_drag = on_drag  # on_drag(True/False) no início/fim do arrasto
            self.dragging = False
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        def mousePressEvent(self, event):
            if self._on_interaction_start:
                self._on_interaction_start("Mover")
            self.dragging = True
            if self._on_drag:
                self._on_drag(True)
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event):
            self.dragging = False
            if self._on_drag:
                self._on_drag(False)
            super().mouseReleaseEvent(event)

        def itemChange(self, change, value):
            # posições definidas por código (auto fit, undo, sessão) não encaixam
            if change == QGraphicsItem.ItemPositionChange and self.dragging and self._snap_fn:
                return self._snap_fn(value)
            if change == QGraphicsItem.ItemPositionHasChanged and self._on_change:
                self._on_change()
            return super().itemChange(change, value)


    class ImageCanvas(QGraphicsView):
        state_changed = Signal(tuple, tuple)
        border_pos_changed = Signal(tuple)
        interaction_started = Signal(str)  # nome do passo de undo
        color_picked = Signal(str, bool)  # cor, só na imagem atual (Shift)
        color_pick_cancelled = Signal()  # Esc no modo Pick Color
        zoom_changed = Signal(float)  # B4: emits zoom factor (1.0 = original size)
        uncovered_changed = Signal(bool)  # parte da custom ficaria transparente

        LOADING_SHOW_DELAY_MS = 150

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setRenderHint(QPainter.Antialiasing)
            self.setRenderHint(QPainter.SmoothPixmapTransform)
            self.setBackgroundBrush(QColor(_theme_tokens()["canvas_bg"]))
            self.setFrameShape(QGraphicsView.NoFrame)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

            self.scene = QGraphicsScene(self)
            self.setScene(self.scene)
            self.scene.setSceneRect(0, 0, 1400, 900)

            self.border_item = QGraphicsRectItem()
            self.border_item.setZValue(10)
            self.scene.addItem(self.border_item)
            # M3: orientação exibida enquanto nenhuma imagem está carregada
            self.empty_hint_item = self.scene.addText(
                "Arraste uma pasta ou imagens aqui\n"
                "Ctrl+O — abrir pasta   ·   Ctrl+V — colar imagem"
            )
            self.empty_hint_item.setDefaultTextColor(QColor(_theme_tokens()["text_muted"]))
            self.empty_hint_item.setZValue(5)
            self.preview_item = QGraphicsPixmapItem()
            self.preview_item.setZValue(12)
            self.preview_item.setVisible(False)
            self.scene.addItem(self.preview_item)
            # guias (terços e centro) dentro da borda: visíveis ao arrastar ou fixas (G)
            self._guides_pinned = False
            self._guide_lines = {}
            guide_pen = QPen(self._guide_color(), 1, Qt.DashLine)
            for name in ("v1", "v2", "vc", "h1", "h2"):
                line = QGraphicsLineItem()
                line.setPen(guide_pen)
                line.setZValue(10.5)
                line.setAcceptedMouseButtons(Qt.NoButton)
                line.setVisible(False)
                self.scene.addItem(line)
                self._guide_lines[name] = line
            # área da borda que a imagem não cobre (sai transparente no export)
            self._uncovered = False
            self.uncovered_item = QGraphicsPathItem()
            hatch = QColor(_theme_tokens()["error"])  # linhas finas: opacas para lerem como vermelho
            self.uncovered_item.setBrush(QBrush(hatch, Qt.BDiagPattern))
            self.uncovered_item.setPen(QPen(Qt.NoPen))
            self.uncovered_item.setZValue(10.6)
            self.uncovered_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(self.uncovered_item)
            self.image_item = None
            self._base_image = None
            self._base_pixmap = None
            self._current_size = None
            self._border_pos = (0, 0)
            self._border_color = "#FFFFFF"
            self._color_pick_enabled = False
            self._loupe = None  # lupa do Pick Color, criada no primeiro uso
            self._zoom_factor = 1.0  # B4
            self._natural_size = None  # M8: tamanho do original (referência do 100%)
            self._last_wheel_time = 0.0  # F8: debounce do snapshot de undo
            # C2: before/after toggle state
            self._before_after_active = False
            self._original_image = None
            self._saved_edit_pos = None
            self._saved_edit_size = None
            # M8: indicador permanente de zoom no canto do canvas
            self._zoom_label = QLabel(self.viewport())
            self._zoom_label.setObjectName("CanvasZoomLabel")
            self._zoom_label.setToolTip(
                "Zoom da imagem em relação ao tamanho natural\n"
                "Roda: ajuste fino · Ctrl+Roda: zoom rápido\n"
                "Ctrl+0: 100% · Alt+B: ajustar à borda"
            )
            self._zoom_label.setVisible(False)
            # M4: indicador de carregamento sobre a borda — só aparece se o
            # carregamento passar de LOADING_SHOW_DELAY_MS, para não piscar
            self._loading = False
            self._loading_dots = 0
            self._loading_label = QLabel(self.viewport())
            self._loading_label.setObjectName("CanvasLoadingLabel")
            self._loading_label.setVisible(False)
            self._loading_show_timer = QTimer(self)
            self._loading_show_timer.setSingleShot(True)
            self._loading_show_timer.setInterval(self.LOADING_SHOW_DELAY_MS)
            self._loading_show_timer.timeout.connect(self._show_loading_label)
            self._loading_anim_timer = QTimer(self)
            self._loading_anim_timer.setInterval(300)
            self._loading_anim_timer.timeout.connect(self._advance_loading_dots)
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
            self._layout_guides()
            if self.empty_hint_item is not None:
                hint_rect = self.empty_hint_item.boundingRect()
                self.empty_hint_item.setPos(
                    (width - hint_rect.width()) / 2,
                    by + BORDA_HEIGHT + 16,
                )
            self.border_pos_changed.emit(self._border_pos)

            if not initial and self.image_item is not None:
                delta_x = bx - old_pos[0]
                delta_y = by - old_pos[1]
                self.image_item.setPos(self.image_item.pos().x() + delta_x, self.image_item.pos().y() + delta_y)
                self._emit_state_changed()

        # ── Guias, encaixe e área vazia ─────────────────────────────────────

        @staticmethod
        def _guide_color():
            color = QColor(_theme_tokens()["text_secondary"])
            color.setAlpha(120)
            return color

        def _layout_guides(self):
            bx, by = self._border_pos
            for name, line in self._guide_lines.items():
                if name.startswith("v"):
                    fraction = {"v1": 1 / 3, "v2": 2 / 3, "vc": 1 / 2}[name]
                    x = bx + BORDA_WIDTH * fraction
                    line.setLine(x, by, x, by + BORDA_HEIGHT)
                else:
                    y = by + BORDA_HEIGHT * (1 / 3 if name == "h1" else 2 / 3)
                    line.setLine(bx, y, bx + BORDA_WIDTH, y)

        def _show_guides(self, visible):
            visible = visible and not self._before_after_active
            for line in self._guide_lines.values():
                line.setVisible(visible)
            if not visible:
                self._highlight_center_guide(False)

        def _highlight_center_guide(self, active):
            color = QColor(_theme_tokens()["accent"]) if active else self._guide_color()
            self._guide_lines["vc"].setPen(QPen(color, 2 if active else 1, Qt.SolidLine if active else Qt.DashLine))

        @property
        def guides_pinned(self):
            return self._guides_pinned

        def set_guides_pinned(self, pinned):
            """Guias sempre visíveis (G) — senão só durante o arrasto."""
            self._guides_pinned = bool(pinned)
            dragging = self.image_item is not None and self.image_item.dragging
            self._show_guides(self._guides_pinned or dragging)

        def _on_image_drag(self, active):
            self._show_guides(active or self._guides_pinned)

        def _snap_position(self, point):
            """Posição proposta pelo arrasto → posição encaixada (Alt desliga)."""
            if self._current_size is None:
                return point
            if QApplication.keyboardModifiers() & Qt.AltModifier:
                self._highlight_center_guide(False)
                return point
            bx, by = self._border_pos
            dx, dy, centered = snap_offsets(
                (point.x(), point.y(), self._current_size[0], self._current_size[1]),
                (bx, by, BORDA_WIDTH, BORDA_HEIGHT),
            )
            self._highlight_center_guide(centered)
            return QPointF(point.x() + dx, point.y() + dy)

        def _update_uncovered(self):
            """Hachura a parte da borda que a imagem não cobre e avisa se mudou."""
            regions = []
            if self.image_item is not None and self._current_size is not None and not self._before_after_active:
                pos = self.image_item.pos()
                regions = uncovered_regions(
                    (pos.x(), pos.y(), self._current_size[0], self._current_size[1]),
                    (self._border_pos[0], self._border_pos[1], BORDA_WIDTH, BORDA_HEIGHT),
                )
            path = QPainterPath()
            for x, y, w, h in regions:
                path.addRect(x, y, w, h)
            self.uncovered_item.setPath(path)
            uncovered = bool(regions)
            if uncovered != self._uncovered:
                self._uncovered = uncovered
                self.uncovered_changed.emit(uncovered)

        @property
        def has_uncovered_area(self):
            return self._uncovered

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._layout_border()
            self._position_zoom_label()
            self._position_loading_label()

        # ── M4: indicador de carregamento ──────────────────────────────────

        @property
        def is_loading(self):
            return self._loading

        def set_loading(self, active):
            """Marca o início/fim do carregamento da imagem exibida."""
            active = bool(active)
            if active == self._loading:
                return
            self._loading = active
            if active:
                # a orientação de "canvas vazio" não faz sentido enquanto carrega
                if self.empty_hint_item is not None:
                    self.empty_hint_item.setVisible(False)
                self._loading_show_timer.start()
            else:
                self._loading_show_timer.stop()
                self._loading_anim_timer.stop()
                self._loading_label.setVisible(False)
                if self.empty_hint_item is not None:
                    self.empty_hint_item.setVisible(self.image_item is None)

        def _show_loading_label(self):
            if not self._loading:
                return
            self._loading_dots = 0
            self._render_loading_text()
            self._loading_label.setVisible(True)
            self._loading_label.raise_()
            self._loading_anim_timer.start()

        def _advance_loading_dots(self):
            self._loading_dots = (self._loading_dots + 1) % 4
            self._render_loading_text()

        def _render_loading_text(self):
            # largura fixa dos pontos evita que o rótulo "dance" a cada quadro
            dots = "." * self._loading_dots
            self._loading_label.setText(f"Carregando{dots}{' ' * (3 - self._loading_dots)}")
            self._position_loading_label()

        def _position_loading_label(self):
            label = self._loading_label
            label.adjustSize()
            bx, by = self._border_pos
            center = self.mapFromScene(bx + BORDA_WIDTH / 2, by + BORDA_HEIGHT / 2)
            label.move(int(center.x() - label.width() / 2), int(center.y() - label.height() / 2))

        def _position_zoom_label(self):
            label = self._zoom_label
            label.adjustSize()
            margin = 10
            viewport_rect = self.viewport().rect()
            label.move(
                viewport_rect.width() - label.width() - margin,
                viewport_rect.height() - label.height() - margin,
            )

        def _update_zoom_label(self):
            if self.image_item is None or self._base_image is None:
                self._zoom_label.setVisible(False)
                return
            self._zoom_label.setText(f"{int(round(self._zoom_factor * 100))}%")
            self._position_zoom_label()
            self._zoom_label.setVisible(True)

        @property
        def zoom_factor(self):
            return self._zoom_factor

        def clear_image(self):
            if self.image_item is not None:
                self.scene.removeItem(self.image_item)
                self.image_item = None
            self._base_image = None
            self._base_pixmap = None
            self._current_size = None
            self._natural_size = None
            self._original_image = None
            self._before_after_active = False
            self._saved_edit_pos = None
            self._saved_edit_size = None
            if self.empty_hint_item is not None:
                self.empty_hint_item.setVisible(not self._loading)
            self._update_zoom_label()
            self._update_uncovered()

        def set_border_color(self, color_hex):
            self._border_color = color_hex
            self.border_item.setPen(QPen(QColor(color_hex), BORDER_THICKNESS))

        def set_color_pick_enabled(self, enabled):
            self._color_pick_enabled = bool(enabled)
            self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
            # a lupa acompanha o cursor só no modo Pick Color
            self.viewport().setMouseTracking(self._color_pick_enabled)
            if not self._color_pick_enabled and self._loupe is not None:
                self._loupe.hide()

        # ── Pick Color: lupa e leitura de pixel ───────────────────────────

        LOUPE_RADIUS = 5  # 11x11 pixels
        LOUPE_ZOOM = 11

        def _image_pixel_at(self, view_pos):
            """(x, y) do pixel de _base_image sob o ponto do viewport, ou None."""
            if self.image_item is None or self._base_image is None:
                return None
            local = self.image_item.mapFromScene(self.mapToScene(view_pos))
            x, y = int(local.x()), int(local.y())
            if 0 <= x < self._base_image.width and 0 <= y < self._base_image.height:
                return x, y
            return None

        def _picked_color(self, x, y, average=False):
            """Hex do pixel (x, y); com `average`, média 3x3 dos pixels opacos."""
            if average:
                box = (max(0, x - 1), max(0, y - 1), min(self._base_image.width, x + 2), min(self._base_image.height, y + 2))
                pixels = [p for p in self._base_image.crop(box).convert("RGBA").getdata() if p[3] > 0]
                if pixels:
                    r, g, b = (round(sum(p[i] for p in pixels) / len(pixels)) for i in range(3))
                    return f"#{r:02x}{g:02x}{b:02x}"
            pixel = self._base_image.getpixel((x, y))
            if isinstance(pixel, int):
                return "#{0:02x}{0:02x}{0:02x}".format(pixel)
            r, g, b = pixel[:3]
            return f"#{r:02x}{g:02x}{b:02x}"

        def _loupe_pixmap(self, x, y):
            """Pixels em volta de (x, y) ampliados, com o central destacado e o hex."""
            from PIL import Image as _Image

            radius, zoom = self.LOUPE_RADIUS, self.LOUPE_ZOOM
            side = radius * 2 + 1
            window = _Image.new("RGBA", (side, side), (0, 0, 0, 0))
            region = self._base_image.crop((x - radius, y - radius, x + radius + 1, y + radius + 1))
            window.paste(region, (0, 0))  # fora da imagem fica transparente
            region.close()
            big = window.resize((side * zoom, side * zoom), _Image.NEAREST)
            window.close()
            color = self._picked_color(x, y)
            text_h = 24
            pixmap = QPixmap(big.width, big.height + text_h)
            pixmap.fill(QColor(_theme_tokens()["surface_elevated"]))
            painter = QPainter(pixmap)
            painter.drawPixmap(0, 0, _pil_to_qpixmap(big))
            big.close()
            grid = QColor(0, 0, 0, 40)
            painter.setPen(QPen(grid, 1))
            for i in range(1, side):
                painter.drawLine(i * zoom, 0, i * zoom, side * zoom)
                painter.drawLine(0, i * zoom, side * zoom, i * zoom)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawRect(radius * zoom, radius * zoom, zoom, zoom)
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.drawRect(radius * zoom - 1, radius * zoom - 1, zoom + 2, zoom + 2)
            painter.fillRect(4, side * zoom + 4, 16, 16, QColor(color))
            painter.setPen(QColor(_theme_tokens()["text_primary"]))
            painter.drawText(26, side * zoom + 17, color.upper())
            painter.end()
            return pixmap

        def _update_loupe(self, view_pos):
            spot = self._image_pixel_at(view_pos)
            if spot is None:
                if self._loupe is not None:
                    self._loupe.hide()
                return
            if self._loupe is None:
                self._loupe = QLabel(self.viewport())
                self._loupe.setObjectName("CanvasLoupe")
                self._loupe.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._loupe.setPixmap(self._loupe_pixmap(*spot))
            self._loupe.adjustSize()
            # 24 px abaixo/à direita do cursor; perto da borda do viewport, do outro lado
            vw, vh = self.viewport().width(), self.viewport().height()
            lw, lh = self._loupe.width(), self._loupe.height()
            px = view_pos.x() + 24 if view_pos.x() + 24 + lw <= vw else view_pos.x() - 24 - lw
            py = view_pos.y() + 24 if view_pos.y() + 24 + lh <= vh else view_pos.y() - 24 - lh
            self._loupe.move(max(0, px), max(0, py))
            self._loupe.show()
            self._loupe.raise_()

        def mouseMoveEvent(self, event):
            if self._color_pick_enabled:
                self._update_loupe(event.position().toPoint())
            super().mouseMoveEvent(event)

        def leaveEvent(self, event):
            if self._loupe is not None:
                self._loupe.hide()
            super().leaveEvent(event)

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
            # B4/M8: zoom relativo ao tamanho do original (o export redimensiona
            # o original para `size`), não à preview — que pode estar ampliada
            natural = self._natural_size or (self._base_image.size if self._base_image else None)
            self._zoom_factor = width / max(1, natural[0]) if natural else 1.0
            self._update_zoom_label()

        def set_image(self, pil_image, state=None, border_color="#FFFFFF", natural_size=None):
            self.clear_image()
            if self.empty_hint_item is not None:
                self.empty_hint_item.setVisible(False)
            self._base_image = pil_image.convert("RGBA")
            self._natural_size = tuple(natural_size) if natural_size else self._base_image.size
            self._original_image = self._base_image.copy()  # C2: keep original
            self._base_pixmap = _pil_to_qpixmap(self._base_image)
            self.set_border_color(border_color)

            pos = state["pos"] if state else self._border_pos
            size = state["size"] if state else self._base_image.size
            self.image_item = _DraggablePixmapItem(
                on_change=self._emit_state_changed,
                on_interaction_start=self.interaction_started.emit,
                snap_fn=self._snap_position,
                on_drag=self._on_image_drag,
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
            self._show_guides(False)
            self._update_uncovered()  # o "antes" não é o enquadramento: sem hachura

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
            self._show_guides(self._guides_pinned)
            self._update_uncovered()

        # ── B4: zoom via wheel ─────────────────────────────────────────────

        def wheelEvent(self, event):
            if self.image_item is None or self._base_image is None:
                super().wheelEvent(event)
                return

            # F8: uma sequência de ticks é um único gesto — só cria snapshot de
            # undo se o último tick foi há mais de 0,5s
            now = time.monotonic()
            if now - self._last_wheel_time > 0.5:
                self.interaction_started.emit("Zoom")
            self._last_wheel_time = now
            delta = event.angleDelta().y()
            if delta == 0:
                event.accept()
                return
            # M8: Ctrl acelera o zoom; o ponto sob o cursor fica parado
            step = ZOOM_STEP_FAST if event.modifiers() & Qt.ControlModifier else ZOOM_STEP_FINE
            factor = step if delta > 0 else 1 / step
            anchor = self.mapToScene(event.position().toPoint())
            self.zoom_by(factor, anchor=(anchor.x(), anchor.y()))
            event.accept()

        def zoom_by(self, factor, anchor=None):
            """Escala a imagem por `factor` em torno de `anchor` (cena); sem
            âncora, usa o centro da imagem."""
            if self.image_item is None or self._current_size is None:
                return
            pos = (self.image_item.pos().x(), self.image_item.pos().y())
            if anchor is None:
                anchor = (pos[0] + self._current_size[0] / 2, pos[1] + self._current_size[1] / 2)
            new_pos, new_size = scaled_placement(pos, self._current_size, factor, anchor)
            self.set_image_state(new_pos, new_size)

        def zoom_to_actual_size(self):
            """M8: volta a imagem a 100% (tamanho do original), centrada no mesmo ponto."""
            if self.image_item is None or self._natural_size is None or self._current_size is None:
                return
            if self._current_size == self._natural_size:
                return
            self.interaction_started.emit("Zoom 100%")
            width, height = self._current_size
            center_x = self.image_item.pos().x() + width / 2
            center_y = self.image_item.pos().y() + height / 2
            natural_w, natural_h = self._natural_size
            self.set_image_state(
                (int(round(center_x - natural_w / 2)), int(round(center_y - natural_h / 2))),
                (natural_w, natural_h),
            )

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Escape and self._color_pick_enabled:
                self.color_pick_cancelled.emit()
                event.accept()
                return
            # deixa ←/→ subirem até a janela para navegar entre imagens (F3)
            if event.key() in (Qt.Key_Left, Qt.Key_Right) and event.modifiers() == Qt.NoModifier:
                event.ignore()
                return
            super().keyPressEvent(event)

        def mousePressEvent(self, event):
            if self._color_pick_enabled:
                spot = self._image_pixel_at(event.position().toPoint())
                if spot is not None:
                    modifiers = event.modifiers()
                    try:
                        # Ctrl: média 3x3 (evita pegar um pixel de ruído de JPEG)
                        color = self._picked_color(*spot, average=bool(modifiers & Qt.ControlModifier))
                    except Exception:
                        color = None
                    if color:
                        # Shift: só nesta imagem (borda individual)
                        self.color_picked.emit(color, bool(modifiers & Qt.ShiftModifier))
                    event.accept()
                    return
            super().mousePressEvent(event)

        def _emit_state_changed(self):
            if self.image_item is None or self._current_size is None:
                return
            if self._before_after_active:
                return
            self._update_uncovered()
            pos = (int(self.image_item.pos().x()), int(self.image_item.pos().y()))
            self.state_changed.emit(pos, self._current_size)
            self.zoom_changed.emit(self._zoom_factor)  # B4: emit on any state change too
else:
    class ImageCanvas:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
