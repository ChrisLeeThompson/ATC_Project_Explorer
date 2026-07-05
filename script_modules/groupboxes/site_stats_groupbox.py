"""
Site Stats GroupBox

The site statistics group box is used to display statistics about the selected lamella site.
The site statistics group box includes:
- QLabels to display:
    - Target thickness
    - Milling angle
    - Lamella width
    - Duration
    - Duration (no lamella placement)
    - Lamella placement duration
    - Preparation duration (no lamella placement)
    - Milling duration
    - Thinning duration
    - Delay duration
"""
import logging
from PySide6.QtWidgets import (
    QGroupBox, QLabel,
    QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import get_site_stats


logger = logging.getLogger(__name__)


class SiteStatsGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, site_data: dict) -> None:
        """Populate the site stats labels from a single site's data.

        Delegates all data extraction and computation to the
        consolidated data reader, then maps the pre-formatted
        results to the display labels.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        stats = get_site_stats(site_data)

        self.target_thickness_result_label.setText(stats.target_thickness)
        self.milling_angle_result_label.setText(stats.milling_angle)
        self.lamella_width_result_label.setText(stats.lamella_width)
        self.duration_result_label.setText(stats.total_duration)
        self.duration_without_placement_result_label.setText(
            stats.duration_without_placement
        )
        self.lamella_placement_duration_result_label.setText(
            stats.lamella_placement_duration
        )
        self.preparation_duration_without_placement_result_label.setText(
            stats.preparation_duration_without_placement
        )
        self.milling_duration_result_label.setText(stats.milling_duration)
        self.thinning_duration_result_label.setText(stats.thinning_duration)
        self.delay_duration_result_label.setText(stats.delay_duration)

    def clear(self) -> None:
        """Reset all site stats labels to their default empty state."""
        self.target_thickness_result_label.setText("")
        self.milling_angle_result_label.setText("")
        self.lamella_width_result_label.setText("")
        self.duration_result_label.setText("")
        self.duration_without_placement_result_label.setText("")
        self.lamella_placement_duration_result_label.setText("")
        self.preparation_duration_without_placement_result_label.setText("")
        self.milling_duration_result_label.setText("")
        self.thinning_duration_result_label.setText("")
        self.delay_duration_result_label.setText("")

    # -----------------------------------------------------------------
    # Widget / Layout Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        # Create labels
        self.target_thickness_label = QLabel("Target thickness", parent=self)
        self.milling_angle_label = QLabel("Milling angle", parent=self)
        self.lamella_width_label = QLabel("Lamella width", parent=self)
        self.duration_label = QLabel("Duration", parent=self)
        self.duration_without_placement_label = QLabel("Duration (no lamella placement)", parent=self)
        self.lamella_placement_duration_label = QLabel("Lamella placement duration", parent=self)
        self.preparation_duration_without_placement_label = QLabel("Preparation duration (no lamella placement)", parent=self)
        self.milling_duration_label = QLabel("Milling duration", parent=self)
        self.thinning_duration_label = QLabel("Thinning duration", parent=self)
        self.delay_duration_label = QLabel("Delay duration", parent=self)
        # Create results labels
        self.target_thickness_result_label = QLabel("", parent=self)
        self.milling_angle_result_label = QLabel("", parent=self)
        self.lamella_width_result_label = QLabel("", parent=self)
        self.duration_result_label = QLabel("", parent=self)
        self.duration_without_placement_result_label = QLabel("", parent=self)
        self.lamella_placement_duration_result_label = QLabel("", parent=self)
        self.preparation_duration_without_placement_result_label = QLabel("", parent=self)
        self.milling_duration_result_label = QLabel("", parent=self)
        self.thinning_duration_result_label = QLabel("", parent=self)
        self.delay_duration_result_label = QLabel("", parent=self)

        labels = [
            self.target_thickness_label,
            self.milling_angle_label,
            self.lamella_width_label,
            self.duration_label,
            self.duration_without_placement_label,
            self.lamella_placement_duration_label,
            self.preparation_duration_without_placement_label,
            self.milling_duration_label,
            self.thinning_duration_label,
            self.delay_duration_label,
            self.target_thickness_result_label,
            self.milling_angle_result_label,
            self.lamella_width_result_label,
            self.duration_result_label,
            self.duration_without_placement_result_label,
            self.lamella_placement_duration_result_label,
            self.preparation_duration_without_placement_result_label,
            self.milling_duration_result_label,
            self.thinning_duration_result_label,
            self.delay_duration_result_label,
        ]
        # Set styles
        for label in labels:
            label.setStyleSheet(AppStyles.Label.default())

    def _setup_layout(self):
        # Layout
        main_layout = QGridLayout(self)
        # Add widgets to layout
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addWidget(self.target_thickness_label, 0, 0)
        main_layout.addWidget(self.target_thickness_result_label, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.milling_angle_label, 1, 0)
        main_layout.addWidget(self.milling_angle_result_label, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.lamella_width_label, 2, 0)
        main_layout.addWidget(self.lamella_width_result_label, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.duration_label, 3, 0)
        main_layout.addWidget(self.duration_result_label, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.duration_without_placement_label, 4, 0)
        main_layout.addWidget(self.duration_without_placement_result_label, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.lamella_placement_duration_label, 5, 0)
        main_layout.addWidget(self.lamella_placement_duration_result_label, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.preparation_duration_without_placement_label, 6, 0)
        main_layout.addWidget(self.preparation_duration_without_placement_result_label, 6, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.milling_duration_label, 7, 0)
        main_layout.addWidget(self.milling_duration_result_label, 7, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.thinning_duration_label, 8, 0)
        main_layout.addWidget(self.thinning_duration_result_label, 8, 1, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.delay_duration_label, 9, 0)
        main_layout.addWidget(self.delay_duration_result_label, 9, 1, alignment=Qt.AlignmentFlag.AlignRight)
        # Set layout and group box style
        self.setLayout(main_layout)
        self.setTitle("Site Statistics")
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)