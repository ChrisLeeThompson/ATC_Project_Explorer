"""
Styled Chart Widget

Base class for matplotlib chart widgets used throughout the
application. Provides shared setup for the matplotlib figure,
canvas, axes styling, and the standard QGroupBox-wrapped layout.

Subclasses implement their own ``populate()`` and ``clear()``
methods, calling the inherited helpers for axes styling and
clearing.

Shared functionality:
    - Dark-themed figure and canvas creation.
    - Axes styling (facecolor, spine colors, label colors, ticks).
    - QGroupBox wrapper with the ``plot()`` stylesheet.
    - ``_clear_axes()`` to reset and restyle.
    - Hover tooltip annotation and highlight rectangle creation.

Usage::

    class MyChart(StyledChartWidget):

        def populate(self, data):
            self.ax.clear()
            self._style_axes()
            # ... plot data ...
            self._create_annotation()
            self.canvas.draw_idle()

        def clear(self):
            self._clear_axes()
"""
import logging
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QSizePolicy
)
from script_modules.app_styles import AppStyles


logger = logging.getLogger(__name__)


class StyledChartWidget(QWidget):
    """Base class for dark-themed matplotlib chart widgets.

    Creates the matplotlib figure, canvas, and axes with
    application-consistent styling, wrapped in a styled
    ``QGroupBox``.

    Subclasses should override ``populate()`` and ``clear()``
    to implement chart-specific rendering logic.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Hover tooltip state (managed by subclasses)
        self._annotation = None
        self._hover_rect = None
        self._create_matplotlib_components()
        self._setup_chart_layout()

    # -----------------------------------------------------------------
    # Matplotlib Setup
    # -----------------------------------------------------------------

    def _create_matplotlib_components(self):
        """Create the matplotlib figure, canvas, and axes."""
        self.figure = Figure(
            facecolor=AppStyles.Colors.MAIN_BG,
            constrained_layout=True,
        )
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.ax = self.figure.add_subplot(111)
        self._style_axes()

        self.figure.patch.set_antialiased(False)
        self.ax.patch.set_antialiased(False)
        self.figure.set_dpi(110)
        self.canvas.setStyleSheet(
            f"background-color: {AppStyles.Colors.MAIN_BG};"
        )

    def _style_axes(self):
        """Apply dark theme styling to the axes.

        Sets the facecolor, spine colors, label colors, and
        tick colors to match the application palette. Hides the
        top and right spines.
        """
        ax = self.ax
        ax.set_facecolor(AppStyles.Colors.MAIN_BG)

        # Spines
        ax.spines["left"].set_color(
            AppStyles.Colors.PLOT_SPINE_COLOR
        )
        ax.spines["bottom"].set_color(
            AppStyles.Colors.PLOT_SPINE_COLOR
        )
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Label and title colors
        ax.xaxis.label.set_color(AppStyles.Colors.TEXT_PRIMARY)
        ax.yaxis.label.set_color(AppStyles.Colors.TEXT_PRIMARY)
        ax.title.set_color(AppStyles.Colors.TEXT_PRIMARY)

        # Tick colors
        ax.tick_params(
            axis="x", colors=AppStyles.Colors.PLOT_SPINE_COLOR
        )
        ax.tick_params(
            axis="y", colors=AppStyles.Colors.PLOT_SPINE_COLOR
        )

    def _setup_chart_layout(self):
        """Build the internal QGroupBox containing the canvas.

        Uses the ``plot()`` groupbox style. Subclasses can
        override this if they need a different layout structure.
        """
        self._group_box = QGroupBox()
        group_box_layout = QVBoxLayout()
        group_box_layout.setContentsMargins(8, 8, 8, 8)
        group_box_layout.addWidget(self.canvas)
        self._group_box.setLayout(group_box_layout)
        self._group_box.setStyleSheet(AppStyles.GroupBox.plot())

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._group_box)
        self.setLayout(layout)
        self.setMinimumHeight(AppStyles.Dimensions.PLOT_MINIMUM_HEIGHT)

    def _clear_axes(self):
        """Clear the axes, restyle, and redraw the blank canvas."""
        self.ax.clear()
        self._style_axes()
        self.canvas.draw_idle()

    # -----------------------------------------------------------------
    # Hover Annotation Helpers
    # -----------------------------------------------------------------

    def _create_annotation(self):
        """Create the hover annotation and highlight rectangle
        (both hidden by default).

        Call this at the end of ``populate()`` after plotting
        data so the annotation renders on top of chart elements.
        """
        self._annotation = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 10),
            textcoords="offset points",
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor=AppStyles.Colors.INPUT_BG,
                edgecolor=AppStyles.Colors.PLOT_SPINE_COLOR,
                alpha=0.95,
            ),
            fontsize=AppStyles.Dimensions.PLOT_TOOLTIP_FONT_SIZE,
            color=AppStyles.Colors.TEXT_PRIMARY,
            zorder=100,
            visible=False,
        )
        self._hover_rect = Rectangle(
            (0, 0), 0, 0,
            linewidth=AppStyles.Dimensions.PLOT_LINE_WIDTH,
            edgecolor=AppStyles.Colors.PLOT_SPINE_COLOR,
            facecolor="none",
            zorder=50,
            visible=False,
        )
        self.ax.add_patch(self._hover_rect)

    def _hide_annotation(self):
        """Hide the hover annotation and highlight rectangle if
        currently visible."""
        needs_redraw = False
        if self._annotation and self._annotation.get_visible():
            self._annotation.set_visible(False)
            needs_redraw = True
        if self._hover_rect and self._hover_rect.get_visible():
            self._hover_rect.set_visible(False)
            needs_redraw = True
        if needs_redraw:
            self.canvas.draw_idle()