"""
Global Stats GroupBox

The global stats group box is used to display statistics about the currently loaded project.
The global stats group box includes:
- QLabels to display:
    - Number of sites in the project
    - Mean target thickness across all sites
    - Mean milling angle across all sites
    - Mean lamella width across all sites
    - Mean duration of all milling operations across all sites
    - Mean duration (no lamella placement)
    - Mean preparation duration
    - Mean lamella placement duration
    - Mean milling duration
    - Mean thinning duration
    - Mean delay duration
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


class GlobalStatsGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
    
    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, metadata: dict) -> None:
        """Populate the global stats labels from consolidated metadata.

        Delegates all data extraction and computation to the
        consolidated data reader, then maps the pre-formatted
        results to the display labels.

        :param metadata: Consolidated metadata dictionary with
            top-level keys ``"ProjectData"`` and ``"Sites"``.
        """
        stats = get_global_stats(metadata)

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
        # Create labels
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
        # Create results labels
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
        # Set layout and group box style
        self.setLayout(main_layout)
        self.setTitle("Global Statistics")
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)