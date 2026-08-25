"""
Site Parameters GroupBox

Composite group box displaying the full SiteProjectData for a
selected lamella site, split into:

    - **Left panel** (fixed): A searchable tree view of all site
      parameters — everything in ``SiteProjectData`` except the
      ``Workflow`` key.
    - **Right panel** (horizontally scrollable): One searchable
      tree view per workflow recipe (e.g. Preparation, Milling,
      Thinning), each in its own titled group box with a fixed
      width.

Each tree view includes a search field and an Expand All checkbox.

Layout::

    SiteParametersGroupBox (titled "Site Parameters")
    ├── Left: QGroupBox ("Parameters")
    │   ├── [Search] [Expand All]
    │   └── QTreeWidget
    └── Right: QScrollArea (horizontal)
        ├── QGroupBox (one per workflow recipe, e.g. "Preparation")
        │   ├── [Search] [Expand All]
        │   └── QTreeWidget
        └── stretch
"""
import logging
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles
from script_modules.widgets.searchable_tree_widget import SearchableTreePanel


logger = logging.getLogger(__name__)


class SiteParametersGroupBox(QGroupBox):
    """Composite group box displaying site parameters (left) and
    per-recipe workflow data (right, horizontally scrollable)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Site Parameters")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._recipe_panels: list[SearchableTreePanel] = []
        self._create_widgets()
        self._setup_layout()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, site_data: dict) -> None:
        """Populate the parameters and recipe trees from a single
        site's data.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        site_name = site_data.get("SiteName", "Unknown")
        self.setTitle(f"{site_name} Site Parameters")

        site_pd = site_data.get("SiteProjectData", {})

        # Left panel: everything except Workflow
        params_data = {
            k: v for k, v in site_pd.items() if k != "Workflow"
        }
        self._params_panel.populate(params_data)

        # Right panel: one panel per recipe
        self._clear_recipe_panels()

        workflow = site_pd.get("Workflow", {})
        recipes = workflow.get("Recipe", [])
        if isinstance(recipes, dict):
            recipes = [recipes]

        for recipe in recipes:
            name = recipe.get("Name", "Recipe")
            panel = SearchableTreePanel(name, parent=self)
            panel.setFixedWidth(
                AppStyles.Dimensions.RECIPE_CARD_FIXED_WIDTH
            )
            panel.apply_style(AppStyles.GroupBox.with_title())
            panel.populate(recipe)
            # Insert before the trailing stretch
            self._recipe_layout.insertWidget(
                self._recipe_layout.count() - 1, panel
            )
            self._recipe_panels.append(panel)

        logger.info(
            f"Site parameters populated for '{site_name}': "
            f"{len(recipes)} recipe(s)"
        )

    def clear(self) -> None:
        """Reset all panels to empty."""
        self.setTitle("Site Parameters")
        self._params_panel.clear_tree()
        self._clear_recipe_panels()
        logger.info("Site parameters cleared")

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create the parameters panel and recipe scroll area."""
        # Left: fixed parameters panel
        self._params_panel = SearchableTreePanel(
            "Parameters", parent=self
        )
        self._params_panel.setMinimumWidth(
            AppStyles.Dimensions.SITE_PARAMETERS_MINIMUM_WIDTH
        )
        self._params_panel.apply_style(
            AppStyles.GroupBox.site_params_with_title()
        )

        # Right: scroll area for recipe panels
        self._recipe_container = QWidget()
        self._recipe_layout = QHBoxLayout(self._recipe_container)
        self._recipe_layout.setContentsMargins(0, 4, 0, 4)
        self._recipe_layout.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )
        self._recipe_layout.addStretch()

        self._recipe_scroll_area = QScrollArea()
        self._recipe_scroll_area.setWidget(self._recipe_container)
        self._recipe_scroll_area.setWidgetResizable(True)
        self._recipe_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._recipe_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._recipe_scroll_area.setStyleSheet(
            AppStyles.ScrollArea.default()
        )

    def _setup_layout(self):
        """Arrange parameters panel (left) and recipe scroll area
        (right) in a horizontal layout."""
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._params_panel)
        content_layout.addWidget(self._recipe_scroll_area, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addLayout(content_layout, 1)
        self.setStyleSheet(AppStyles.GroupBox.plot_with_title())
        self.setMinimumHeight(AppStyles.Dimensions.RECIPE_CARD_MINIMUM_HEIGHT)

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _clear_recipe_panels(self):
        """Remove and delete all dynamically created recipe panels."""
        for panel in self._recipe_panels:
            self._recipe_layout.removeWidget(panel)
            panel.deleteLater()
        self._recipe_panels.clear()