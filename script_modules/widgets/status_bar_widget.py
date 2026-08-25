"""
Status Bar

Status bar with a message label, a progress bar shown during parsing
and loading operations, and a Cancel button for stopping them.
"""
from PySide6.QtWidgets import (
    QStatusBar, QLabel, QProgressBar,
    QWidget, QSizePolicy
)
from PySide6.QtCore import QTimer, Signal, Slot
from script_modules.app_styles import AppStyles
from script_modules.widgets.button_widgets import CancelButton


class StatusBarWidget(QStatusBar):

    # Signal emitted when the Cancel button is clicked.
    cancel_button_clicked_signal: Signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._clear_status_bar_message)
        self._create_widgets()
        self._connect_widgets()
        self._setup_layout()
        self._set_initial_state()

    def _create_widgets(self):
        self.status_bar_label = QLabel()
        self.status_bar_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.progress_bar = QProgressBar()
        self.cancel_button = CancelButton()
        self.status_bar_label.setStyleSheet(AppStyles.Label.status_bar())
        self.progress_bar.setStyleSheet(AppStyles.ProgressBar.default())

    def _connect_widgets(self):
        self.cancel_button.clicked.connect(self.cancel_button_clicked_signal.emit)

    def _setup_layout(self):
        self.addWidget(self.status_bar_label, 3)
        self.addWidget(self.progress_bar, 2)
        spacer = QWidget()
        spacer.setStyleSheet("background: transparent; border: none;")
        self.addPermanentWidget(spacer, 1)
        self.addPermanentWidget(self.cancel_button)
        self.setStyleSheet(AppStyles.StatusBar.default())

    def _set_initial_state(self):
        self.set_status_bar_message_timed("Hello!", 10000)
        self.set_progress_bar_visible(False)
        self.set_cancel_button_visible(False)

    @Slot(str)
    def set_status_bar_message(self, message: str):
        """Set the status bar QLabel text.

        Cancels any pending timed-message timer so a stale timer
        from an earlier ``set_status_bar_message_timed`` call cannot
        blank this (untimed) text mid-operation.
        """
        self._message_timer.stop()
        self.status_bar_label.setText(message)

    @Slot(str, int)
    def set_status_bar_message_timed(self, message: str, timeout: int):
        """Set the status bar QLabel text, cleared after *timeout* ms."""
        self._message_timer.stop()
        self.status_bar_label.setText(message)
        self._message_timer.start(timeout)

    def _clear_status_bar_message(self):
        self.status_bar_label.setText("")

    @Slot(bool)
    def set_progress_bar_visible(self, visible: bool):
        self.progress_bar.setVisible(visible)

    @Slot(bool)
    def set_cancel_button_visible(self, visible: bool):
        self.cancel_button.setVisible(visible)

    @Slot(int, int)
    def set_progress_bar_range(self, minimum: int, maximum: int):
        self.progress_bar.setRange(minimum, maximum)

    @Slot(int)
    def set_progress_bar_value(self, value: int):
        self.progress_bar.setValue(value)