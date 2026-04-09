QT_AVAILABLE = False
PYSIDE_IMPORT_ERROR = None

try:
    from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
    from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTransform
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QGraphicsItem,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListView,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QDialogButtonBox,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except Exception as exc:  # pragma: no cover - exercised only when Qt is unavailable
    PYSIDE_IMPORT_ERROR = exc


def qt_unavailable_error():
    detail = f": {PYSIDE_IMPORT_ERROR}" if PYSIDE_IMPORT_ERROR else ""
    return RuntimeError(f"PySide6 is not available{detail}")
