"""
Central repository for application styles and tool tips.
"""
from pathlib import Path


# =====================================================================
# Asset Paths
# =====================================================================

# Centralized asset directory path. All modules that need icon
# or image assets should reference this rather than computing
# their own relative paths.
ASSETS_DIR = Path(__file__).parent.parent / "script_assets"
ICON_PATH = ASSETS_DIR / "catbug_waiting_color.png"


# =====================================================================
# Scrollbar Style Helpers
# =====================================================================

def _vertical_scrollbar(bg_color: str, prefix: str = "") -> str:
    """Generate a vertical scrollbar CSS block.

    :param bg_color: Background color for the scrollbar track.
    :param prefix: Optional parent selector prefix
        (e.g. ``"QTextEdit "``). Include a trailing space.
    :return: CSS string for a styled vertical scrollbar.
    """
    p = prefix
    return f"""
            {p}QScrollBar:vertical {{
                background-color: {bg_color};
                width: {StyleDimensions.SCROLLBAR_WIDTH};
                margin: 0px;
                border-radius: 6px;
            }}
            {p}QScrollBar::handle:vertical {{
                background-color: {StyleColors.BUTTON_BG};
                border-radius: 4px;
                min-height: {StyleDimensions.SCROLLBAR_HANDLE_MIN};
                margin: 2px;
                border: none;
            }}
            {p}QScrollBar::handle:vertical:hover {{
                background-color: {StyleColors.BUTTON_HOVER};
            }}
            {p}QScrollBar::handle:vertical:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
            }}
            {p}QScrollBar::add-line:vertical,
            {p}QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            {p}QScrollBar::add-page:vertical,
            {p}QScrollBar::sub-page:vertical {{
                background: none;
            }}"""


def _horizontal_scrollbar(bg_color: str, prefix: str = "") -> str:
    """Generate a horizontal scrollbar CSS block.

    :param bg_color: Background color for the scrollbar track.
    :param prefix: Optional parent selector prefix.
        Include a trailing space if non-empty.
    :return: CSS string for a styled horizontal scrollbar.
    """
    p = prefix
    return f"""
            {p}QScrollBar:horizontal {{
                background-color: {bg_color};
                height: {StyleDimensions.SCROLLBAR_WIDTH};
                margin: 0px;
                border-radius: 6px;
            }}
            {p}QScrollBar::handle:horizontal {{
                background-color: {StyleColors.BUTTON_BG};
                border-radius: 4px;
                min-width: {StyleDimensions.SCROLLBAR_HANDLE_MIN};
                margin: 2px;
                border: none;
            }}
            {p}QScrollBar::handle:horizontal:hover {{
                background-color: {StyleColors.BUTTON_HOVER};
            }}
            {p}QScrollBar::handle:horizontal:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
            }}
            {p}QScrollBar::add-line:horizontal,
            {p}QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            {p}QScrollBar::add-page:horizontal,
            {p}QScrollBar::sub-page:horizontal {{
                background: none;
            }}"""


class StyleColors:
    
    MAIN_BG = "#273945"
    GROUPBOX_BG = "#34454f"
    INPUT_BG = "#1f2d36"
    INPUT_BORDER = "#0f1e28"
    BUTTON_BG = "#476273"
    BUTTON_HOVER = "#2ea2ec"
    BUTTON_PRESSED = "#1F6FA1"
    BUTTON_DISABLED = "#3d5462"
    TEXT_PRIMARY = "#ffffff"
    TEXT_DISABLED = "#8498a4"
    # Plot colors
    PLOT_LINE_COLOR = "#eb70a9" # plot line color, v2.5: #38003c, catbug: a1c7ea (blue), bright_blue: 9df1ed, catbug (glove): eb70a9, TEM blue: #00CEC8
    PLOT_SPINE_COLOR = "#ffffff"
    PLOT_PREPARATION_BAR_COLOR = "#2D67ED" #302DED" #"#2D67ED"
    PLOT_MILLING_BAR_COLOR = "#2EA2EC"
    PLOT_THINNING_BAR_COLOR = "#2DE0ED"
    PLOT_LAMELLA_PLACEMENT_BAR_COLOR = "#F0A830" #"#f0a830" #2DEDBA" #"#CC7722" #"#13265C"
    PLOT_DELAY_BAR_COLOR = "#1F6FA1"
    IMAGE_VIEWER_CROSSHAIR_COLOR = "#00CEC8" #"eb70a9"
    SITE_POSITION_PLOT_MARKER_COLOR = "#2EA2EC"
    SITE_POSITION_PLOT_MARKER_EDGE_COLOR = "#ffffff"


class StyleDimensions:

    WINDOW_WIDTH = 1640
    WINDOW_HEIGHT = 1040
    BORDER_RADIUS_LARGE = "8.0px"
    BORDER_RADIUS_SMALL = "4.0px"
    MARGIN = "8px"
    PADDING = "4px"
    MAIN_WINDOW_MARGIN = 4
    TAB_PADDING = "10px"
    FONT_SIZE_NORMAL = "11pt"
    FONT_SIZE_LARGE = "14pt"
    FONT_SIZE_EXTRA_LARGE = "16pt"
    BUTTON_WIDTH = 180
    LAYOUT_CONTENTS_MARGIN = 8
    LAYOUT_HSPACING = 60
    LAYOUT_VSPACING = 10
    CHECKBOX_SPACING = "16px"
    COMBOBOX_WIDTH = 180
    SCROLLBAR_WIDTH = "12px"
    SCROLLBAR_HANDLE_MIN = "30px"
    SPLITTER_HANDLE_WIDTH = 6
    # Plot dimensions
    PLOT_MINIMUM_HEIGHT = 400
    PLOT_LINE_WIDTH = 1.0
    PLOT_TITLE_FONT_SIZE = 11
    PLOT_LABEL_FONT_SIZE = 10
    PLOT_TOOLTIP_FONT_SIZE = 10
    # Pattern viewer dimensions
    PATTERN_VIEWER_MINIMUM_HEIGHT = 620
    PATTERN_VIEWER_CANVAS_MINIMUM_HEIGHT = 400
    PATTERN_VIEWER_LEFT_COLUMN_WIDTH = 400
    PATTERN_VIEWER_RIGHT_COLUMN_WIDTH = 220
    # Image viewer dimensions
    IMAGE_VIEWER_CANVAS_MINIMUM_HEIGHT = 200
    IMAGE_VIEWER_COMBOBOX_WIDTH = 400
    IMAGE_VIEWER_GROUPBOX_MINIMUM_HEIGHT = 640
    # Image metadata dimensions
    IMAGE_METADATA_MINIMUM_HEIGHT = 400
    # Site parameters dimensions
    SITE_PARAMETERS_MINIMUM_WIDTH = 460
    RECIPE_CARD_MINIMUM_HEIGHT = 660
    RECIPE_CARD_FIXED_WIDTH = 560
    # Site position plot dimensions
    SITE_POSITION_PLOT_MINIMUM_HEIGHT = 800
    MARKER_SIZE_DEFAULT = 40
    MARKER_SIZE_HOVER = 80
    # Plot export dimensions
    EXPORT_PNG_DPI = 200
    # Collapsible widget dimensions
    COLLAPSIBLE_HANDLE_WIDTH = 10
    COLLAPSIBLE_ARROW_SIZE = 4
    COLLAPSIBLE_ARROW_PEN_WIDTH = 1.5


class StyleFonts:

    FONT_COURIER = "Courier"


class ApplicationText:

    WINDOW_TITLE = "ATC Project Explorer 1.1"

    GLOBAL_SITE_LABEL = "Global Project Data"
    

class ToolTips:

    @staticmethod
    def default() -> str:
        """Shared tooltip style block for widget stylesheets."""
        return f"""
            QToolTip {{
                background-color: {StyleColors.BUTTON_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_LARGE};
            }}
        """


class WindowStyles:

    @staticmethod
    def window() -> str:
        return f"""
            QMainWindow {{
                background-color: {StyleColors.MAIN_BG}
            }}
        """
    
    @staticmethod
    def tabs() -> str:
        return f"""
            QTabWidget::pane {{
                border: 1px solid {StyleColors.MAIN_BG};
                background-color: {StyleColors.MAIN_BG};
            }}
            QTabBar::tab {{
                background: {StyleColors.MAIN_BG};
                color: {StyleColors.TEXT_PRIMARY};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                margin: {StyleDimensions.MARGIN};
                padding: {StyleDimensions.TAB_PADDING};
            }}
            QTabBar::tab:hover {{
                color: {StyleColors.BUTTON_HOVER};
            }}
            QTabBar::tab:selected {{
                background-color: {StyleColors.GROUPBOX_BG};
                margin: {StyleDimensions.MARGIN};
                padding: {StyleDimensions.TAB_PADDING};
            }}
        """


class LabelStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QLabel {{
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
            }}
            {ToolTips.default()}
        """

    @staticmethod
    def large_label() -> str:
        return f"""
            QLabel {{
                font-size: {StyleDimensions.FONT_SIZE_LARGE};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            {ToolTips.default()}
        """
    
    @staticmethod
    def status_bar() -> str:
        return f"""
            QLabel {{
                font-size: {StyleDimensions.FONT_SIZE_LARGE};
                background-color: {StyleColors.MAIN_BG};
                color: {StyleColors.TEXT_PRIMARY};
                margin-left: {StyleDimensions.MARGIN};
                padding-left: {StyleDimensions.PADDING};
            }}
        """


class GroupBoxStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QGroupBox {{
                /* border: 1px solid {StyleColors.INPUT_BORDER}; */
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.GROUPBOX_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: {StyleDimensions.PADDING};
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
            }}
        """

    @staticmethod
    def with_title() -> str:
        return f"""
            QGroupBox {{
                /* border: 1px solid {StyleColors.INPUT_BORDER}; */
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.GROUPBOX_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: 30px;
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
                /* font-weight: bold;*/
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 6px;
                margin-top: 4px;
                padding: 0 10px;
                background-color: {StyleColors.GROUPBOX_BG};
            }}
        """
    
    @staticmethod
    def with_title_bold() -> str:
        return f"""
            QGroupBox {{
                /* border: 1px solid {StyleColors.INPUT_BORDER}; */
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.GROUPBOX_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: 30px;
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
                font-weight: bold;
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 6px;
                margin-top: 4px;
                padding: 0 10px;
                background-color: {StyleColors.GROUPBOX_BG};
            }}
        """
    
    @staticmethod
    def default_main_background() -> str:
        return f"""
            QGroupBox {{
                /* border: 1px solid {StyleColors.INPUT_BORDER}; */
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {AppStyles.Colors.MAIN_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: {StyleDimensions.PADDING};
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
            }}
        """
    
    @staticmethod
    def plot_area() -> str:
        return f"""
            QGroupBox {{
                border: 2px solid transparent;
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.MAIN_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: {StyleDimensions.PADDING};
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
            }}
        """
    
    @staticmethod
    def plot() -> str:
        return f"""
            QGroupBox {{
                border: 2px solid {StyleColors.GROUPBOX_BG};
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.MAIN_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: {StyleDimensions.PADDING};
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
            }}
        """
    
    @staticmethod
    def plot_with_title() -> str:
        return f"""
            QGroupBox {{
                border: 2px solid {StyleColors.GROUPBOX_BG};
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.MAIN_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: 30px;
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
                font-weight: bold;
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 6px;
                margin-top: 4px;
                padding: 0 10px;
                background-color: {StyleColors.MAIN_BG};
            }}
        """

    @staticmethod
    def embedded() -> str:
        """Borderless groupbox with a visible title used as a section
        header inside a parent container (e.g. SliceDataGroupBox)."""
        return f"""
            QGroupBox {{
                border: none;
                border-radius: 0px;
                background-color: transparent;
                margin: 0px;
                padding-top: 22px;
                padding-left: 0px;
                padding-right: 0px;
                padding-bottom: 0px;
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 0px;
                margin-top: 2px;
                padding: 0 4px;
                color: {StyleColors.TEXT_PRIMARY};
            }}
        """

    @staticmethod
    def embedded_untitled() -> str:
        """Borderless groupbox without a title, used for self-describing
        content (e.g. ImageViewerGroupBox) inside a parent container."""
        return f"""
            QGroupBox {{
                border: none;
                border-radius: 0px;
                background-color: transparent;
                margin: 0px;
                padding: 0px;
            }}
        """
    
    @staticmethod
    def site_params_with_title() -> str:
        return f"""
            QGroupBox {{
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.GROUPBOX_BG};
                margin-top: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                margin-bottom: 4px;
                padding-top: 30px;
                padding-left: {StyleDimensions.PADDING};
                padding-right: {StyleDimensions.PADDING};
                padding-bottom: {StyleDimensions.PADDING};
                /*font-weight: bold;*/
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 6px;
                margin-top: 4px;
                padding: 0 10px;
                background-color: {StyleColors.GROUPBOX_BG};
            }}
        """


class ButtonStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QPushButton {{
                background-color: {StyleColors.BUTTON_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.BUTTON_BG};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                margin-top: 4px;
                margin-bottom: 4px;
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
            }}
            QPushButton:hover {{
                background-color: {StyleColors.BUTTON_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {StyleColors.BUTTON_DISABLED};
                color: {StyleColors.TEXT_DISABLED};
            }}
            {ToolTips.default()}
        """
    
    @staticmethod
    def reset_view() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {StyleColors.TEXT_DISABLED};
                border: none;
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: {StyleColors.BUTTON_BG};
                color: {StyleColors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
                color: {StyleColors.TEXT_PRIMARY};
            }}
        """

    @staticmethod
    def toggle() -> str:
        return f"""
            QPushButton {{
                background-color: {AppStyles.Colors.BUTTON_BG};
                color: {AppStyles.Colors.TEXT_PRIMARY};
                border: 1px solid transparent;
                border-radius: {AppStyles.Dimensions.BORDER_RADIUS_SMALL};
                margin: {AppStyles.Dimensions.MARGIN};
                padding: {AppStyles.Dimensions.PADDING};
                font-size: {AppStyles.Dimensions.FONT_SIZE_NORMAL};
            }}
            QPushButton:hover {{
                background-color: {AppStyles.Colors.BUTTON_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {AppStyles.Colors.BUTTON_PRESSED};
            }}
            QPushButton:checked {{
                background-color: {AppStyles.Colors.BUTTON_HOVER};
            }}
            QPushButton:checked:hover {{
                background-color: {AppStyles.Colors.BUTTON_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {AppStyles.Colors.BUTTON_BG};
                color: {AppStyles.Colors.TEXT_DISABLED};
            }}
            """


class SpinBoxStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QSpinBox {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
            }}
            QSpinBox:focus {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QSpinBox:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                height: 0px;
            }}
        """


class CheckBoxStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QCheckBox {{
                color: {StyleColors.TEXT_PRIMARY};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                spacing: {StyleDimensions.CHECKBOX_SPACING};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
                padding: {StyleDimensions.PADDING};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                border: 1px solid {StyleColors.INPUT_BORDER};
                background-color: {StyleColors.INPUT_BG};
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QCheckBox::indicator:checked {{
                background-color: {StyleColors.BUTTON_HOVER};
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QCheckBox:disabled {{
                color: {StyleColors.TEXT_DISABLED};
            }}
            QCheckBox::indicator:disabled {{
                background-color: {StyleColors.BUTTON_DISABLED};
            }}
            {ToolTips.default()}
        """


class ComboBoxStyles:

    # Arrow icon path (uses centralized ASSETS_DIR)
    _arrow_path = str(ASSETS_DIR / "down_arrow_white.svg").replace("\\", "/")

    @staticmethod
    def default() -> str:
        return f"""
            QComboBox {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
            }}
            QComboBox:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 40px;
            }}
            QComboBox::down-arrow {{
                image: url({ComboBoxStyles._arrow_path});
                width: 16px;
                height: 16px;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
                outline: none;
                selection-background-color: transparent;
                selection-color: {StyleColors.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 8px;
                border: 1px solid {StyleColors.INPUT_BORDER};
                outline: none;
            }}
            QComboBox QAbstractItemView::item:hover {{
                padding: 8px 8px;
                background-color: {StyleColors.BUTTON_BG};
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: transparent;
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
            }}
            QComboBox QAbstractItemView::item:selected:hover {{
                background-color: {StyleColors.BUTTON_BG};
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
            }}
            {_vertical_scrollbar(StyleColors.INPUT_BG, prefix="QComboBox QAbstractItemView ")}
        """
    
    @staticmethod
    def checkable() -> str:
        return f"""
            QComboBox {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
            }}
            QComboBox:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 40px;
            }}
            QComboBox::down-arrow {{
                image: url({ComboBoxStyles._arrow_path});
                width: 16px;
                height: 16px;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
                outline: none;
                selection-background-color: transparent;
                selection-color: {StyleColors.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 8px;
                border: 1px solid {StyleColors.INPUT_BORDER};
                outline: none;
            }}
            QComboBox QAbstractItemView::item:hover {{
                padding: 8px 8px;
                background-color: {StyleColors.BUTTON_BG};
                border: 1px solid {StyleColors.INPUT_BORDER};
                /* border-radius: {StyleDimensions.BORDER_RADIUS_SMALL}; */
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: transparent;
                border: 1px solid {StyleColors.INPUT_BORDER};
            }}
            QComboBox QAbstractItemView::indicator {{
                width: 18px;
                height: 18px;
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                border: 1px solid {StyleColors.BUTTON_HOVER};
                background-color: {StyleColors.INPUT_BG};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView::indicator:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QComboBox QAbstractItemView::indicator:checked {{
                background-color: {StyleColors.BUTTON_HOVER};
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            {_vertical_scrollbar(StyleColors.INPUT_BG, prefix="QComboBox QAbstractItemView ")}
        """
    
    @staticmethod
    def context_menu() -> str:
        return f"""
            QMenu {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: 4px 0px;
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {StyleColors.BUTTON_BG};
            }}
            QMenu::item:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {StyleColors.INPUT_BORDER};
                margin: 4px 8px;
            }}
        """


class ScrollAreaStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QScrollArea {{
                background-color: {StyleColors.MAIN_BG};
                border: none;
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {StyleColors.MAIN_BG};
            }}
            {_vertical_scrollbar(StyleColors.MAIN_BG)}
            {_horizontal_scrollbar(StyleColors.GROUPBOX_BG)}
        """

    @staticmethod
    def plot_button_scroll_area() -> str:
        return f"""
            QScrollArea {{
                background-color: {StyleColors.MAIN_BG};
                border: none;
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {StyleColors.GROUPBOX_BG};
            }}
            {_vertical_scrollbar(StyleColors.GROUPBOX_BG)}
            {_horizontal_scrollbar(StyleColors.GROUPBOX_BG)}
        """

    @staticmethod
    def embedded() -> str:
        """Scroll area styled for embedding inside a QGroupBox
        (GROUPBOX_BG background throughout)."""
        return f"""
            QScrollArea {{
                background-color: {StyleColors.GROUPBOX_BG};
                border: none;
                border-radius: 0px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {StyleColors.GROUPBOX_BG};
            }}
            {_vertical_scrollbar(StyleColors.GROUPBOX_BG)}
        """

    @staticmethod
    def horizontal_only() -> str:
        """Style for horizontal-only scroll areas (e.g., for long file paths)."""
        return f"""
                QScrollArea {{
                    background-color: transparent;
                    border: none;
                }}
                QScrollArea > QWidget > QWidget {{
                    background-color: transparent;
                }}
                {_horizontal_scrollbar(StyleColors.MAIN_BG)}
            """


class ProgressBarStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QProgressBar {{
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                background-color: {StyleColors.INPUT_BG};
                text-align: center;
                color: {StyleColors.TEXT_PRIMARY};
                height: 20px;
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
            }}
            QProgressBar::chunk {{
                background-color: {StyleColors.BUTTON_HOVER};
                border-radius: 2px;
                margin: 1px;
            }}
        """


class LineEditStyles:

    @staticmethod
    def line_edit() -> str:
        return f"""
            QLineEdit {{
                background-color: transparent;
                border: 1px solid {StyleColors.BUTTON_BG};
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                color: {StyleColors.TEXT_PRIMARY};
                padding: {StyleDimensions.PADDING};
                font-family: {StyleFonts.FONT_COURIER};
                font-size: {StyleDimensions.FONT_SIZE_LARGE};
                selection-background-color: {StyleColors.BUTTON_HOVER};
            }}
        """

    @staticmethod
    def search() -> str:
        return f"""
            QLineEdit {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: 1px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                margin-left: {StyleDimensions.MARGIN};
                margin-right: {StyleDimensions.MARGIN};
            }}
            QLineEdit:hover {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
            QLineEdit:focus {{
                border: 1px solid {StyleColors.BUTTON_HOVER};
            }}
        """


class StatusBarStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QStatusBar {{
                background-color: {StyleColors.MAIN_BG};
                border: none;
                margin: {StyleDimensions.MARGIN};
            }}
            QStatusBar::item {{
                background-color: transparent;
                border: none;
            }}
        """


class TreeWidgetStyles:

    # Arrow icon paths (use centralized ASSETS_DIR)
    _down_arrow_path = str(ASSETS_DIR / "filled_down_arrow_white.svg").replace("\\", "/")
    _right_arrow_path = str(ASSETS_DIR / "filled_right_arrow_white.svg").replace("\\", "/")

    @staticmethod
    def metadata() -> str:
        return f"""
            QTreeWidget {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: none;
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 2px 0px;
            }}
            QTreeWidget::item:selected {{
                background-color: {StyleColors.BUTTON_BG};
            }}
            QTreeWidget::item:hover {{
                background-color: {StyleColors.BUTTON_BG};
            }}
            QHeaderView {{
                background-color: {StyleColors.INPUT_BG};
            }}
            QHeaderView::section {{
                background-color: {StyleColors.INPUT_BG};
                color: {StyleColors.TEXT_PRIMARY};
                border: none;
                border-right: 2px solid {StyleColors.BUTTON_BG};
                padding: 0px;
                margin: 0px;
                min-height: 16px;
                max-height: 16px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QTreeWidget::branch {{
                background-color: {StyleColors.INPUT_BG};
            }}
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {{
                border-image: none;
                image: url({TreeWidgetStyles._right_arrow_path});
                width: 16px;
                height: 16px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
            }}
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {{
                border-image: none;
                image: url({TreeWidgetStyles._down_arrow_path});
                width: 16px;
                height: 16px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
            }}
            {_vertical_scrollbar(StyleColors.INPUT_BG)}
            {_horizontal_scrollbar(StyleColors.INPUT_BG)}
        """


class TextEditStyles:
    """Styles for QTextEdit widgets."""

    @staticmethod
    def metadata() -> str:
        """Read-only text display for raw image metadata."""
        return f"""
            QTextEdit {{
                background-color: {StyleColors.INPUT_BG};
                border: none;
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                color: {StyleColors.TEXT_PRIMARY};
                padding: {StyleDimensions.PADDING};
                font-family: {StyleFonts.FONT_COURIER};
                font-size: {StyleDimensions.FONT_SIZE_EXTRA_LARGE};
                selection-background-color: {StyleColors.BUTTON_HOVER};
            }}
            {_vertical_scrollbar(StyleColors.INPUT_BG, prefix="QTextEdit ")}
            {_horizontal_scrollbar(StyleColors.INPUT_BG, prefix="QTextEdit ")}
        """


class SplitterStyles:

    @staticmethod
    def horizontal() -> str:
        """Style for a horizontal QSplitter used in the image viewer."""
        return f"""
            QSplitter::handle:horizontal {{
                background-color: {StyleColors.BUTTON_BG};
                width: {StyleDimensions.SPLITTER_HANDLE_WIDTH}px;
                border-radius: 4px;
                margin-top: 0px;
                margin-bottom: 0px;
                border: none;
            }}
            QSplitter::handle:horizontal:hover {{
                background-color: {StyleColors.BUTTON_HOVER};
            }}
            QSplitter::handle:horizontal:pressed {{
                background-color: {StyleColors.BUTTON_PRESSED};
            }}
        """


class AppStyles:

    Colors = StyleColors
    Dimensions = StyleDimensions
    Window = WindowStyles
    GroupBox = GroupBoxStyles
    Label = LabelStyles
    Button = ButtonStyles
    SpinBox = SpinBoxStyles
    AppText = ApplicationText
    AppToolTips = ToolTips
    CheckBox = CheckBoxStyles
    ComboBox = ComboBoxStyles
    ScrollArea = ScrollAreaStyles
    ProgressBar = ProgressBarStyles
    StatusBar = StatusBarStyles
    LineEdit = LineEditStyles
    TextEdit = TextEditStyles
    TreeWidget = TreeWidgetStyles
    Splitter = SplitterStyles

    @staticmethod
    def apply_toolbar_icon_color(toolbar, color: str = StyleColors.TEXT_PRIMARY) -> None:
        """Force all NavigationToolbar2QT icons to a specific color.

        Matplotlib toolbar icons are dark-on-transparent PNGs. On Windows with
        a light system theme Qt may also apply palette tinting, leaving icons
        dark against the app's dark toolbar background. This method repaints
        every action icon using SourceIn composition: the icon silhouette
        (alpha channel) is preserved while all opaque pixels are filled with
        `color`, making the result theme-independent.

        Call this once immediately after ``NavigationToolbar2QT(canvas, parent)``
        is constructed.

        Args:
            toolbar: A ``NavigationToolbar2QT`` instance.
            color:   Any Qt-parseable color string (default: ``TEXT_PRIMARY``
                     white, ``"#ffffff"``).
        """
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        from PySide6.QtCore import Qt

        target_color = QColor(color)
        icon_size = toolbar.iconSize()

        for action in toolbar.actions():
            icon = action.icon()
            if icon.isNull():
                continue

            # Prefer the exact icon size used by the toolbar; fall back to the
            # first available size if the toolbar size is not listed.
            sizes = icon.availableSizes()
            size = icon_size if icon_size in sizes or not sizes else sizes[0]

            source_pm = icon.pixmap(size)
            if source_pm.isNull():
                continue

            # Paint a new pixmap: draw the original (preserving shape), then
            # flood-fill the opaque region with the target colour.
            colored_pm = QPixmap(source_pm.size())
            colored_pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(colored_pm)
            painter.drawPixmap(0, 0, source_pm)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(colored_pm.rect(), target_color)
            painter.end()

            action.setIcon(QIcon(colored_pm))