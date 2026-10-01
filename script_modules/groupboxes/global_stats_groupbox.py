"""
Global Stats GroupBox

Group box (titled "Global Statistics") listing project-wide values:
number of sites, mean target thickness, mean milling angle, mean
lamella width, and the mean duration breakdown (total, without
lamella placement, lamella placement, preparation without lamella
placement, milling, thinning, delay).

Below those rows, an activities section lists the mean duration of
every activity across the sites (each site's runs of an activity
summed, then averaged over the sites that ran it).  The content
scrolls inside the groupbox, whose height is fixed.

The statistics can be computed from a subset of sites (the site
selection lives in the owning panel, which re-populates on change);
the groupbox title and the section header reflect whether a subset
is active.
"""
import logging
from PySide6.QtWidgets import (
    QGroupBox, QLabel, QWidget, QScrollArea,
    QGridLayout, QVBoxLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import (
    ActivityMean,
    get_activity_duration_means,
    get_global_stats,
)


logger = logging.getLogger(__name__)


# Groupbox titles: default (empty/cleared), all sites selected, and
# a proper subset selected (including the empty selection).
_TITLE_DEFAULT = "Global Statistics"
_TITLE_ALL = "Global Statistics: All Sites"
_TITLE_SUBSET = "Global Statistics: Selected Sites"

# Activities section header, following the same switch.
_ACTIVITIES_HEADER_ALL = "All Sites Activities (mean durations)"
_ACTIVITIES_HEADER_SUBSET = "Selected Sites Activities (mean durations)"

# Grid row of the activities header; activity rows follow it.
_ACTIVITIES_HEADER_ROW = 11


class _ContentWidthScrollArea(QScrollArea):
    """Vertical scroll area whose width hint follows its content.

    ``QScrollArea.sizeHint`` caps itself at 36 font heights wide, which
    is narrower than the statistics rows; the groupbox sizes itself
    from this hint, so the rows would be clipped.  The height hint is
    irrelevant here: the groupbox has a fixed height.
    """

    def sizeHint(self) -> QSize:
        content = self.widget()
        if content is None:
            return super().sizeHint()
        hint = content.sizeHint()
        width = hint.width() + 2 * self.frameWidth()
        if (
            self.verticalScrollBarPolicy()
            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ):
            width += self.verticalScrollBar().sizeHint().width()
        return QSize(width, hint.height() + 2 * self.frameWidth())


class GlobalStatsGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._activity_rows: list[tuple[QLabel, QLabel]] = []
        self._create_widgets()
        self._setup_layout()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(
        self,
        metadata: dict,
        selected_sites: set[str] | None = None,
    ) -> None:
        """Populate the global stats labels from consolidated metadata.

        Delegates all data extraction and computation to the
        consolidated data reader, then maps the pre-formatted
        results to the display labels.

        :param metadata: Consolidated metadata dictionary with
            top-level keys ``"ProjectData"`` and ``"Sites"``.
        :param selected_sites: Site names to compute the statistics
            from, or *None* for all sites. The statistics are
            recomputed over the subset (``get_global_stats`` is a
            pure function of the ``Sites`` list) and the groupbox
            title and the activities header reflect whether a
            proper subset is active.
        """
        sites = metadata.get("Sites", [])
        if selected_sites is None:
            shown = sites
        else:
            shown = [
                s for s in sites
                if s.get("SiteName", "Unknown") in selected_sites
            ]

        all_shown = selected_sites is None or len(shown) == len(sites)
        self.setTitle(_TITLE_ALL if all_shown else _TITLE_SUBSET)
        self.activities_header_label.setText(
            _ACTIVITIES_HEADER_ALL if all_shown
            else _ACTIVITIES_HEADER_SUBSET
        )

        subset = {**metadata, "Sites": shown}
        stats = get_global_stats(subset)

        self.number_of_sites_result_label.setText(stats.num_sites)
        self.mean_target_thickness_result_label.setText(stats.mean_target_thickness)
        self.mean_milling_angle_result_label.setText(stats.mean_milling_angle)
        self.mean_lamella_width_result_label.setText(stats.mean_lamella_width)
        self.mean_duration_result_label.setText(stats.mean_total_duration)
        self.mean_duration_without_placement_result_label.setText(
            stats.mean_duration_without_placement
        )
        self.mean_lamella_placement_duration_result_label.setText(stats.mean_lamella_placement_duration)
        self.mean_preparation_duration_without_placement_result_label.setText(stats.mean_preparation_duration_without_placement)
        self.mean_milling_duration_result_label.setText(stats.mean_total_milling_duration)
        self.mean_thinning_duration_result_label.setText(stats.mean_total_thinning_duration)
        self.mean_delay_duration_result_label.setText(stats.mean_total_delay_duration)

        self._populate_activity_rows(get_activity_duration_means(subset))

    def clear(self) -> None:
        """Reset all result labels to their default empty state."""
        self.setTitle(_TITLE_DEFAULT)
        self.number_of_sites_result_label.setText("")
        self.mean_target_thickness_result_label.setText("")
        self.mean_milling_angle_result_label.setText("")
        self.mean_lamella_width_result_label.setText("")
        self.mean_duration_result_label.setText("")
        self.mean_duration_without_placement_result_label.setText("")
        self.mean_lamella_placement_duration_result_label.setText("")
        self.mean_preparation_duration_without_placement_result_label.setText("")
        self.mean_milling_duration_result_label.setText("")
        self.mean_thinning_duration_result_label.setText("")
        self.mean_delay_duration_result_label.setText("")
        self.activities_header_label.setText("")
        self._clear_activity_rows()

    def activity_rows(self) -> list[tuple[str, str]]:
        """The activities section as ``(name, mean)`` texts."""
        return [
            (name.text(), mean.text())
            for name, mean in self._activity_rows
        ]

    # -----------------------------------------------------------------
    # Activities Section
    # -----------------------------------------------------------------

    def _populate_activity_rows(self, means: list[ActivityMean]) -> None:
        """Rebuild the activity rows below the section header.

        :param means: ``ActivityMean`` list from the reader, in
            display order.
        """
        self._clear_activity_rows()
        for offset, mean in enumerate(means, start=1):
            row = _ACTIVITIES_HEADER_ROW + offset
            name_label = QLabel(mean.name, parent=self)
            mean_label = QLabel(mean.mean_duration, parent=self)
            for label in (name_label, mean_label):
                label.setStyleSheet(AppStyles.Label.default())
            self._grid.addWidget(name_label, row, 0)
            self._grid.addWidget(
                mean_label, row, 1,
                alignment=Qt.AlignmentFlag.AlignRight,
            )
            self._activity_rows.append((name_label, mean_label))
        self._scroll_area.updateGeometry()

    def _clear_activity_rows(self) -> None:
        """Remove the activity rows."""
        for labels in self._activity_rows:
            for label in labels:
                self._grid.removeWidget(label)
                label.deleteLater()
        self._activity_rows.clear()
        # The scroll area's width hint follows the rows; tell the
        # owning layout so the groupbox is not left at its old width.
        self._scroll_area.updateGeometry()

    # -----------------------------------------------------------------
    # Widget / Layout Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        self.number_of_sites_label = QLabel("Number of sites", parent=self)
        self.mean_target_thickness_label = QLabel("Mean target thickness", parent=self)
        self.mean_milling_angle_label = QLabel("Mean milling angle", parent=self)
        self.mean_lamella_width_label = QLabel("Mean lamella width", parent=self)
        self.mean_duration_label = QLabel("Mean duration", parent=self)
        self.mean_duration_without_placement_label = QLabel("Mean duration (no lamella placement)", parent=self)
        self.mean_lamella_placement_duration_label = QLabel("Mean lamella placement duration", parent=self)
        self.mean_preparation_duration_without_placement_label = QLabel("Mean preparation duration (no lamella placement)", parent=self)
        self.mean_milling_duration_label = QLabel("Mean milling duration", parent=self)
        self.mean_thinning_duration_label = QLabel("Mean thinning duration", parent=self)
        self.mean_delay_duration_label = QLabel("Mean delay duration", parent=self)
        self.number_of_sites_result_label = QLabel("", parent=self)
        self.mean_target_thickness_result_label = QLabel("", parent=self)
        self.mean_milling_angle_result_label = QLabel("", parent=self)
        self.mean_lamella_width_result_label = QLabel("", parent=self)
        self.mean_duration_result_label = QLabel("", parent=self)
        self.mean_duration_without_placement_result_label = QLabel("", parent=self)
        self.mean_lamella_placement_duration_result_label = QLabel("", parent=self)
        self.mean_preparation_duration_without_placement_result_label = QLabel("", parent=self)
        self.mean_milling_duration_result_label = QLabel("", parent=self)
        self.mean_thinning_duration_result_label = QLabel("", parent=self)
        self.mean_delay_duration_result_label = QLabel("", parent=self)
        self.activities_header_label = QLabel("", parent=self)

        labels = [
            self.number_of_sites_label,
            self.mean_target_thickness_label,
            self.mean_milling_angle_label,
            self.mean_lamella_width_label,
            self.mean_duration_label,
            self.mean_duration_without_placement_label,
            self.mean_preparation_duration_without_placement_label,
            self.mean_lamella_placement_duration_label,
            self.mean_milling_duration_label,
            self.mean_thinning_duration_label,
            self.mean_delay_duration_label,
            self.number_of_sites_result_label,
            self.mean_target_thickness_result_label,
            self.mean_milling_angle_result_label,
            self.mean_lamella_width_result_label,
            self.mean_duration_result_label,
            self.mean_duration_without_placement_result_label,
            self.mean_preparation_duration_without_placement_result_label,
            self.mean_lamella_placement_duration_result_label,
            self.mean_milling_duration_result_label,
            self.mean_thinning_duration_result_label,
            self.mean_delay_duration_result_label,
        ]
        for label in labels:
            label.setStyleSheet(AppStyles.Label.default())
        self.activities_header_label.setStyleSheet(
            AppStyles.Label.section_header()
        )

    def _setup_layout(self):
        # The rows live on a content widget inside a scroll area; the
        # groupbox itself keeps a fixed height.
        content = QWidget(parent=self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        self._grid.addWidget(self.number_of_sites_label, 0, 0)
        self._grid.addWidget(self.number_of_sites_result_label, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_target_thickness_label, 1, 0)
        self._grid.addWidget(self.mean_target_thickness_result_label, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_milling_angle_label, 2, 0)
        self._grid.addWidget(self.mean_milling_angle_result_label, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_lamella_width_label, 3, 0)
        self._grid.addWidget(self.mean_lamella_width_result_label, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_duration_label, 4, 0)
        self._grid.addWidget(self.mean_duration_result_label, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_duration_without_placement_label, 5, 0)
        self._grid.addWidget(self.mean_duration_without_placement_result_label, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_lamella_placement_duration_label, 6, 0)
        self._grid.addWidget(self.mean_lamella_placement_duration_result_label, 6, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_preparation_duration_without_placement_label, 7, 0)
        self._grid.addWidget(self.mean_preparation_duration_without_placement_result_label, 7, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_milling_duration_label, 8, 0)
        self._grid.addWidget(self.mean_milling_duration_result_label, 8, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_thinning_duration_label, 9, 0)
        self._grid.addWidget(self.mean_thinning_duration_result_label, 9, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.mean_delay_duration_label, 10, 0)
        self._grid.addWidget(self.mean_delay_duration_result_label, 10, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(
            self.activities_header_label, _ACTIVITIES_HEADER_ROW, 0, 1, 2
        )
        # Reserve the value column so the groupbox width does not jump
        # between "N/A" and durations.
        probe = QLabel("00:00:00")
        probe.setStyleSheet(AppStyles.Label.default())
        probe.ensurePolished()
        self._grid.setColumnMinimumWidth(1, probe.sizeHint().width())
        content_layout.addLayout(self._grid)
        # Keep the rows top-aligned when the content is shorter than
        # the viewport.
        content_layout.addStretch(1)

        self._scroll_area = _ContentWidthScrollArea(parent=self)
        self._scroll_area.setWidget(content)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_area.setStyleSheet(AppStyles.ScrollArea.embedded())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN
        )
        main_layout.addWidget(self._scroll_area)
        self.setTitle(_TITLE_DEFAULT)
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(
            AppStyles.Dimensions.GLOBAL_STATS_GROUPBOX_HEIGHT
        )
