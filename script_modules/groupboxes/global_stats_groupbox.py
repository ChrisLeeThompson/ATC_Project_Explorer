"""
Global Stats GroupBox

Group box (titled "Global Statistics") listing project-wide values:
number of sites, mean target thickness, mean milling angle, mean
lamella width, and the mean duration breakdown (total, without
lamella placement, lamella placement, preparation without lamella
placement, milling, thinning, delay).

The statistics can be computed from a subset of sites (the site
selection lives in the owning panel, which re-populates on change);
the groupbox title reflects whether a subset is active.
"""
import logging
from PySide6.QtWidgets import (
    QGroupBox, QLabel,
    QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import get_global_stats


logger = logging.getLogger(__name__)


# Groupbox titles: default (empty/cleared), all sites selected, and
# a proper subset selected (including the empty selection).
_TITLE_DEFAULT = "Global Statistics"
_TITLE_ALL = "Global Statistics: All Sites"
_TITLE_SUBSET = "Global Statistics: Selected Sites"


class GlobalStatsGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
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
            title reflects whether a proper subset is active.
        """
        sites = metadata.get("Sites", [])
        if selected_sites is None:
            shown = sites
        else:
            shown = [
                s for s in sites
                if s.get("SiteName", "Unknown") in selected_sites
            ]

        self.setTitle(
            _TITLE_ALL
            if selected_sites is None or len(shown) == len(sites)
            else _TITLE_SUBSET
        )

        stats = get_global_stats({**metadata, "Sites": shown})

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

    def _setup_layout(self):
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addWidget(self.number_of_sites_label, 0, 0)
        main_layout.addWidget(self.number_of_sites_result_label, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_target_thickness_label, 1, 0)
        main_layout.addWidget(self.mean_target_thickness_result_label, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_milling_angle_label, 2, 0)
        main_layout.addWidget(self.mean_milling_angle_result_label, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_lamella_width_label, 3, 0)
        main_layout.addWidget(self.mean_lamella_width_result_label, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_duration_label, 4, 0)
        main_layout.addWidget(self.mean_duration_result_label, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_duration_without_placement_label, 5, 0)
        main_layout.addWidget(self.mean_duration_without_placement_result_label, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_lamella_placement_duration_label, 6, 0)
        main_layout.addWidget(self.mean_lamella_placement_duration_result_label, 6, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_preparation_duration_without_placement_label, 7, 0)
        main_layout.addWidget(self.mean_preparation_duration_without_placement_result_label, 7, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_milling_duration_label, 8, 0)
        main_layout.addWidget(self.mean_milling_duration_result_label, 8, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_thinning_duration_label, 9, 0)
        main_layout.addWidget(self.mean_thinning_duration_result_label, 9, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.mean_delay_duration_label, 10, 0)
        main_layout.addWidget(self.mean_delay_duration_result_label, 10, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(main_layout)
        self.setTitle(_TITLE_DEFAULT)
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)