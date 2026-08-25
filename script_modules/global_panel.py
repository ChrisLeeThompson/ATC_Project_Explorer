"""
Global Panel

Composite panel for displaying global (project-wide) data: the
global statistics, a horizontally scrollable strip of site-preview
cards, the per-site process-duration bar chart, and the
site-position atlas, all inside a vertical scroll area.
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from script_modules.app_styles import AppStyles
from script_modules.groupboxes.global_stats_groupbox import GlobalStatsGroupBox
from script_modules.groupboxes.global_site_preview_groupbox import (
    GlobalSitePreviewGroupBox,
)
from script_modules.widgets.duration_barchart_widget import DurationBarChartWidget
from script_modules.widgets.site_position_plot_widget import SitePositionPlotWidget


logger = logging.getLogger(__name__)


class GlobalPanel(QWidget):

    # Re-exposed from the child widgets (atlas, duration chart,
    # preview cards) so the main module can connect without
    # reaching into them.
    site_selected = Signal(str)
    site_open_new_window = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Last-populated metadata, kept so the Global Statistics can
        # be recomputed when the site selection changes.
        self._metadata: dict | None = None
        # Canonical selected-site set, keyed by SiteName. The panel
        # is the single writer; children render it and report user
        # intent. Duplicate SiteNames collapse to one entry.
        self._selected_site_names: set[str] = set()
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Set the project root for resolving image paths in
        the site preview cards.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self.global_site_preview_groupbox.set_project_root(
            project_root
        )

    def set_preloaded_media(self, media: dict | None) -> None:
        """Forward the preloaded media bundle to the child widgets
        that can consume it (preview cards and the spatial atlas).

        Must be called before :meth:`populate` to take effect.  When
        *None*, both children fall back to on-demand image loading.

        :param media: Mapping ``{site_name: {...}}`` from
            ``preview_media_loader.load_project_media``, or *None*.
        """
        self.global_site_preview_groupbox.set_preloaded_media(media)
        self.site_position_plot.set_preloaded_media(media)

    def populate(self, metadata: dict) -> None:
        """Populate all child groupboxes with consolidated metadata.

        :param metadata: Consolidated metadata dictionary with
            top-level keys ``"ProjectData"`` and ``"Sites"``.
        """
        # Every (re)load resets the site selection to all sites.
        self._metadata = metadata
        self._selected_site_names = self._all_site_names()
        self.global_stats_groupbox.populate(metadata)
        self.global_site_preview_groupbox.populate(metadata)
        self.duration_bar_chart.populate(metadata)
        self.site_position_plot.populate(metadata)
        logger.info("GlobalPanel populated")

    def clear(self) -> None:
        """Reset all child groupboxes to their default empty state."""
        self._metadata = None
        self._selected_site_names = set()
        self.global_stats_groupbox.clear()
        self.global_site_preview_groupbox.clear()
        self.duration_bar_chart.clear()
        self.site_position_plot.clear()
        logger.info("GlobalPanel cleared")

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create child groupboxes owned by this panel."""
        self.global_stats_groupbox = GlobalStatsGroupBox(parent=self)
        self.global_site_preview_groupbox = (
            GlobalSitePreviewGroupBox(parent=self)
        )
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
        self.duration_bar_chart.site_selected.connect(
            self.site_selected
        )
        self.duration_bar_chart.site_open_new_window.connect(
            self.site_open_new_window
        )
        self.global_site_preview_groupbox.site_selected.connect(
            self.site_selected
        )
        # The chart's checkboxes drive the Global Statistics selection.
        self.duration_bar_chart.site_check_toggled.connect(
            self._on_site_check_toggled
        )
        self.duration_bar_chart.select_all_requested.connect(
            self._on_select_all_sites
        )
        self.duration_bar_chart.deselect_all_requested.connect(
            self._on_deselect_all_sites
        )

    # -----------------------------------------------------------------
    # Site selection coordination
    # -----------------------------------------------------------------

    def _all_site_names(self) -> set[str]:
        """Every site name in the last-populated metadata."""
        if self._metadata is None:
            return set()
        return {
            site.get("SiteName", "Unknown")
            for site in self._metadata.get("Sites", [])
        }

    def _on_site_check_toggled(self, site_name: str, checked: bool) -> None:
        """One chart row checkbox was toggled by the user."""
        if self._metadata is None:
            return
        if checked:
            self._selected_site_names.add(site_name)
        else:
            self._selected_site_names.discard(site_name)
        # Push the set back so duplicate-named rows stay coherent
        # (set_site_selection never emits).
        self.duration_bar_chart.set_site_selection(
            self._selected_site_names
        )
        self._refresh_global_stats()

    def _on_select_all_sites(self) -> None:
        """Select All requested (chart master checkbox)."""
        if self._metadata is None:
            return
        self._selected_site_names = self._all_site_names()
        self.duration_bar_chart.set_site_selection(
            self._selected_site_names
        )
        self._refresh_global_stats()

    def _on_deselect_all_sites(self) -> None:
        """Deselect All requested (chart master checkbox)."""
        if self._metadata is None:
            return
        self._selected_site_names = set()
        self.duration_bar_chart.set_site_selection(
            self._selected_site_names
        )
        self._refresh_global_stats()

    def _refresh_global_stats(self) -> None:
        """Recompute the Global Statistics from the selection."""
        if self._metadata is None:
            return
        self.global_stats_groupbox.populate(
            self._metadata, set(self._selected_site_names)
        )

    def _setup_layout(self):
        """Build the scroll area and internal content layout."""
        # Top row: stats (fixed width) + site previews (expanding)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(self.global_stats_groupbox)
        top_row.addWidget(self.global_site_preview_groupbox, 1)

        top_row_container = QWidget()
        top_row_container.setLayout(top_row)
        top_row_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(top_row_container)
        content_layout.addWidget(self.duration_bar_chart)
        content_layout.addWidget(self.site_position_plot)
        content_layout.addStretch(1)

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

        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        panel_layout.addWidget(self._scroll_area)