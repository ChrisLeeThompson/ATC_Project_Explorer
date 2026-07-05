"""
Site Panel

Composite panel for displaying site-specific (per-lamella) data.

The module includes:
- Scrollable QWidget
- Groupboxes:
    - SiteStatsGroupBox: Displays site-specific statistics
    - SitePreviewGroupBox: Side-by-side preview of the
      electron evaluation and last polishing images
    - PatternViewerGroupBox: Three-column pattern viewer with
      info panel, schematic canvas, and activity toggle buttons
    - SiteParametersGroupBox: Displays site parameters and
      per-recipe workflow data in searchable tree views
    - ImageViewerGroupBox: Two-column image browser with
      directory selection and Previous/Next navigation
- Widgets:
    - SiteActivityBarChartWidget: Horizontal bar chart of
      per-activity durations
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Slot
from script_modules.app_styles import AppStyles
from script_modules.groupboxes.site_stats_groupbox import SiteStatsGroupBox
from script_modules.groupboxes.site_preview_groupbox import SitePreviewGroupBox
from script_modules.groupboxes.site_parameters_groupbox import SiteParametersGroupBox
from script_modules.groupboxes.image_viewer_groupbox import ImageViewerGroupBox
from script_modules.groupboxes.pattern_viewer_groupbox import PatternViewerGroupBox
from script_modules.widgets.site_activity_barchart_widget import SiteActivityBarChartWidget


logger = logging.getLogger(__name__)


class SitePanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create child widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
        # Wire inter-widget signals
        self._connect_signals()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Set the project root path for resolving relative image
        paths. Delegates to the image viewer and site preview
        groupboxes.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self.image_viewer_groupbox.set_project_root(project_root)
        self.site_preview_groupbox.set_project_root(project_root)

    def populate(self, site_data: dict) -> None:
        """Populate all child groupboxes with a single site's data.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list, containing keys such as
            ``"SiteName"``, ``"SiteProjectData"``, ``"Statistics"``,
            and ``"ImageDirectories"``.
        """
        self.site_stats_groupbox.populate(site_data)
        self.site_preview_groupbox.populate(site_data)
        self.site_activity_bar_chart.populate(site_data)
        self.pattern_viewer_groupbox.populate(site_data)
        self.image_viewer_groupbox.populate(site_data)
        self.site_parameters_groupbox.populate(site_data)
        site_name = site_data.get("SiteName", "Unknown")
        logger.info(f"SitePanel populated for site '{site_name}'")

    def clear(self) -> None:
        """Reset all child groupboxes to their default empty state."""
        self.site_stats_groupbox.clear()
        self.site_preview_groupbox.clear()
        self.site_activity_bar_chart.clear()
        self.pattern_viewer_groupbox.clear()
        self.image_viewer_groupbox.clear()
        self.site_parameters_groupbox.clear()
        logger.info("SitePanel cleared")

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create child groupboxes owned by this panel."""
        self.site_stats_groupbox = SiteStatsGroupBox(parent=self)
        self.site_preview_groupbox = SitePreviewGroupBox(parent=self)
        self.site_activity_bar_chart = SiteActivityBarChartWidget(parent=self)
        self.pattern_viewer_groupbox = PatternViewerGroupBox(parent=self)
        self.image_viewer_groupbox = ImageViewerGroupBox(parent=self)
        self.site_parameters_groupbox = SiteParametersGroupBox(parent=self)

    def _setup_layout(self):
        """Build the scroll area and internal content layout."""
        # Top row: stats (fixed width) + preview (expanding)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(self.site_stats_groupbox)
        top_row.addWidget(self.site_preview_groupbox, 1)

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
        content_layout.addWidget(self.site_activity_bar_chart)
        content_layout.addWidget(self.pattern_viewer_groupbox)
        content_layout.addWidget(self.image_viewer_groupbox, 1)
        content_layout.addWidget(self.site_parameters_groupbox, 1)
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

    def _connect_signals(self):
        """Wire inter-widget signals."""
        self.site_preview_groupbox.preview_clicked.connect(
            self._on_preview_clicked
        )

    # -----------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------

    @Slot(str, str)
    def _on_preview_clicked(
        self, directory_name: str, filename: str
    ) -> None:
        """Scroll to the image viewer and select the clicked
        preview image.

        :param directory_name: Source directory name
            (e.g. ``"LamellaEvaluationImages"``).
        :param filename: Image file name to navigate to.
        """
        # Scroll the image viewer into view
        self._scroll_area.ensureWidgetVisible(
            self.image_viewer_groupbox, 0, 50
        )
        # Select the directory and image
        self.image_viewer_groupbox.select_image(
            directory_name, filename
        )