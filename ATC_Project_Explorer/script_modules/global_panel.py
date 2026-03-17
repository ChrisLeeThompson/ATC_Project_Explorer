"""
Global Panel

Composite panel for displaying global (project-wide) data.

The module includes:
- Scrollable QWidget
- Groupboxes:
    - GlobalStatsGroupBox: Displays global project statistics
- Widgets:
    - DurationBarChartWidget: Horizontal stacked bar chart of
      per-site milling durations
    - SitePositionPlotWidget: Spatial atlas of lamella site
      positions with optional SEM image montage
"""
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from script_modules.app_styles import AppStyles
from script_modules.groupboxes.global_stats_groupbox import GlobalStatsGroupBox
from script_modules.widgets.duration_barchart_widget import DurationBarChartWidget
from script_modules.widgets.site_position_plot_widget import SitePositionPlotWidget


logger = logging.getLogger(__name__)


class GlobalPanel(QWidget):

    # Re-exposed from SitePositionPlotWidget so the main module
    # can connect without reaching into child widgets.
    site_selected = Signal(str)
    site_open_new_window = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create child widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
        # Connect child signals
        self._connect_signals()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, metadata: dict) -> None:
        """Populate all child groupboxes with consolidated metadata.

        :param metadata: Consolidated metadata dictionary with
            top-level keys ``"ProjectData"`` and ``"Sites"``.
        """
        self.global_stats_groupbox.populate(metadata)
        self.duration_bar_chart.populate(metadata)
        self.site_position_plot.populate(metadata)
        logger.info("GlobalPanel populated")

    def clear(self) -> None:
        """Reset all child groupboxes to their default empty state."""
        self.global_stats_groupbox.clear()
        self.duration_bar_chart.clear()
        self.site_position_plot.clear()
        logger.info("GlobalPanel cleared")

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create child groupboxes owned by this panel."""
        self.global_stats_groupbox = GlobalStatsGroupBox(parent=self)
        self.duration_bar_chart = DurationBarChartWidget(parent=self)
        self.site_position_plot = SitePositionPlotWidget(parent=self)

    def _connect_signals(self):
        """Wire child widget signals to panel-level signals."""
        self.site_position_plot.site_selected.connect(
            self.site_selected
        )
        self.site_position_plot.site_open_new_window.connect(
            self.site_open_new_window
        )

    def _setup_layout(self):
        """Build the scroll area and internal content layout."""
        # Top row: stats (fixed width) — ready for additional
        # widgets to be added beside it in the future.
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(self.global_stats_groupbox)
        top_row.addStretch(1)

        top_row_container = QWidget()
        top_row_container.setLayout(top_row)
        top_row_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        # Content widget that lives inside the scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(top_row_container)
        content_layout.addWidget(self.duration_bar_chart)
        content_layout.addWidget(self.site_position_plot)
        content_layout.addStretch(1)

        # Scroll area wrapping the content widget
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(content_widget)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_area.setStyleSheet(
            AppStyles.ScrollArea.default()
        )

        # Panel-level layout: just the scroll area
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        panel_layout.addWidget(self._scroll_area)