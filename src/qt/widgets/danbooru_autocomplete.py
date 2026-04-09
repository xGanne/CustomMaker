import concurrent.futures
import logging

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QEvent, QListWidget, QListWidgetItem, QObject, QPoint, QTimer, Qt, Signal


logger = logging.getLogger(__name__)


if QT_AVAILABLE:
    class DanbooruAutocomplete(QObject):
        suggestions_ready = Signal(int, object)

        def __init__(self, entry_widget, client):
            super().__init__(entry_widget)
            self.entry = entry_widget
            self.client = client
            self.popup = QListWidget(entry_widget.window())
            self.popup.setWindowFlag(Qt.ToolTip, True)
            self.popup.setFocusPolicy(Qt.NoFocus)
            self.popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.popup.setSelectionMode(QListWidget.SingleSelection)
            self.popup.hide()
            self.popup.itemClicked.connect(self._apply_item)

            self.timer = QTimer(self.entry)
            self.timer.setSingleShot(True)
            self.timer.setInterval(250)
            self.timer.timeout.connect(self._fetch_suggestions)

            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tag_suggest")
            self._query_seq = 0
            self._active_query_seq = 0
            self._current_word = ""
            self.suggestions_ready.connect(self._apply_suggestions)

            self.entry.textEdited.connect(self._on_text_edited)
            self.entry.installEventFilter(self)
            self.popup.installEventFilter(self)

        def close(self):
            self.timer.stop()
            self.popup.hide()
            self._executor.shutdown(wait=False, cancel_futures=True)

        def eventFilter(self, obj, event):
            if obj is self.entry and event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Down and self.popup.isVisible() and self.popup.count() > 0:
                    self.popup.setFocus()
                    self.popup.setCurrentRow(0)
                    return True
                if (
                    event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab)
                    and self.popup.isVisible()
                    and self.popup.hasFocus()
                ):
                    item = self.popup.currentItem()
                    if item is not None:
                        self._apply_item(item)
                        return True
                if event.key() == Qt.Key_Escape and self.popup.isVisible():
                    self.popup.hide()
                    return True
                if self.popup.isVisible() and event.key() in (
                    Qt.Key_Backspace,
                    Qt.Key_Delete,
                    Qt.Key_Left,
                    Qt.Key_Right,
                    Qt.Key_Home,
                    Qt.Key_End,
                    Qt.Key_Space,
                ):
                    QTimer.singleShot(0, self.timer.start)

            if obj is self.popup and event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                    item = self.popup.currentItem()
                    if item is not None:
                        self._apply_item(item)
                    return True
                if event.key() == Qt.Key_Escape:
                    self.popup.hide()
                    self.entry.setFocus()
                    return True
            return False

        def _on_text_edited(self, _text):
            self.timer.start()

        def _current_token(self):
            cursor_pos = self.entry.cursorPosition()
            text = self.entry.text()
            before_cursor = text[:cursor_pos]
            token = before_cursor.split(" ")[-1].strip()
            return token

        def _fetch_suggestions(self):
            token = self._current_token()
            if len(token) < 2:
                self.popup.hide()
                return

            self._current_word = token
            self._query_seq += 1
            query_seq = self._query_seq
            self._active_query_seq = query_seq

            future = self._executor.submit(self.client.fetch_tags, token)

            def on_done(done_future):
                try:
                    suggestions = done_future.result()
                except Exception as exc:
                    logger.debug("Autocomplete falhou: %s", exc)
                    suggestions = []
                self.suggestions_ready.emit(query_seq, suggestions)

            future.add_done_callback(on_done)

        def _apply_suggestions(self, query_seq, suggestions):
            if query_seq != self._active_query_seq:
                return
            if not suggestions:
                self.popup.hide()
                return
            self.popup.clear()
            for suggestion in suggestions:
                self.popup.addItem(QListWidgetItem(suggestion))
            self.popup.setCurrentRow(0)
            self._show_popup()

        def _show_popup(self):
            width = max(self.entry.width(), 280)
            row_height = self.popup.sizeHintForRow(0) if self.popup.count() > 0 else 24
            height = min(220, max(40, row_height * min(8, self.popup.count()) + 8))
            below = self.entry.mapToGlobal(QPoint(0, self.entry.height()))
            self.popup.setGeometry(below.x(), below.y(), width, height)
            self.popup.show()
            self.popup.raise_()

        def _apply_item(self, item):
            selection = item.text()
            cursor_pos = self.entry.cursorPosition()
            full_text = self.entry.text()
            text_before = full_text[:cursor_pos]
            text_after = full_text[cursor_pos:]
            last_space_index = text_before.rfind(" ")
            if last_space_index == -1:
                new_before = selection + " "
            else:
                new_before = text_before[: last_space_index + 1] + selection + " "
            final_text = new_before + text_after
            self.entry.setText(final_text)
            self.entry.setCursorPosition(len(new_before))
            self.popup.hide()
            self.entry.setFocus()
else:
    class DanbooruAutocomplete:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
