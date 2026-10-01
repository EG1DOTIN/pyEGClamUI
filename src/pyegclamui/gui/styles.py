"""
Modern QSS theme stylesheets for pyEGClamUI.
Provides cohesive, dark and light visual aesthetics without inline CSS fragmentation.
"""

DARK_THEME_QSS = """
/* Global Window & Typography */
QWidget {
    background-color: #1e1f22;
    color: #e0e2e8;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

QLabel {
    background-color: transparent;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #313338;
    background-color: #1e1f22;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #2b2d31;
    color: #949ba4;
    padding: 8px 16px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}

QTabBar::tab:hover {
    background-color: #35373c;
    color: #f2f3f5;
}

QTabBar::tab:selected {
    background-color: #1e1f22;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}

/* Group Boxes / Cards */
QGroupBox {
    border: 1px solid #313338;
    border-radius: 8px;
    margin-top: 18px;
    padding: 16px;
    font-weight: bold;
    color: #38bdf8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
}

/* Push Buttons - Standard Base Style (Slate Neutral with Pure White Font) */
QPushButton {
    background-color: #334155;
    color: #ffffff;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #475569;
    color: #ffffff;
    border-color: #64748b;
}

QPushButton:pressed {
    background-color: #1e293b;
    color: #ffffff;
}

QPushButton:disabled {
    background-color: #1e293b;
    color: #64748b;
    border-color: #0f172a;
}

/* Primary Action Buttons (Sky Blue with Pure White Font) */
QPushButton#primaryButton {
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
    font-size: 13px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton#primaryButton:hover {
    background-color: #0ea5e9;
    border-color: #7dd3fc;
    color: #ffffff;
}

QPushButton#primaryButton:pressed {
    background-color: #0369a1;
    color: #ffffff;
}

/* Danger / Destructive Action Buttons (Light Crimson Red with Pure White Font) */
QPushButton#dangerButton {
    background-color: #dc2626;
    color: #ffffff;
    border: 1px solid #ef4444;
    font-weight: 600;
}

QPushButton#dangerButton:hover {
    background-color: #ef4444;
    border-color: #f87171;
    color: #ffffff;
}

QPushButton#dangerButton:pressed {
    background-color: #b91c1c;
    color: #ffffff;
}

/* Success / Recovery Action Buttons (Emerald Green with Pure White Font) */
QPushButton#successButton {
    background-color: #16a34a;
    color: #ffffff;
    border: 1px solid #22c55e;
    font-weight: 600;
}

QPushButton#successButton:hover {
    background-color: #22c55e;
    border-color: #4ade80;
    color: #ffffff;
}

QPushButton#successButton:pressed {
    background-color: #15803d;
    color: #ffffff;
}

/* Secondary / Utility Action Buttons (Slate Neutral with Pure White Font) */
QPushButton#secondaryButton {
    background-color: #334155;
    color: #ffffff;
    border: 1px solid #475569;
    font-weight: 600;
}

QPushButton#secondaryButton:hover {
    background-color: #475569;
    border-color: #64748b;
    color: #ffffff;
}

QPushButton#secondaryButton:pressed {
    background-color: #1e293b;
    color: #ffffff;
}

/* Scroll Area & Viewport */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* Scan Hub Horizontal Cards */
QFrame#scanCard {
    background-color: #111214;
    border: 1px solid #313338;
    border-radius: 10px;
}

QFrame#scanCard:hover {
    border-color: #0284c7;
    background-color: #14161a;
}

QFrame#scanCard QLabel {
    background-color: transparent;
    border: none;
    padding: 0px;
}

QFrame#scanCard QPushButton#primaryButton {
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 600;
    min-height: 22px;
}

/* Status Banner Card */
QFrame#bannerCard {
    background-color: #111214;
    border: 1px solid #166534;
    border-radius: 12px;
}

QFrame#bannerCard QLabel {
    background-color: transparent;
    border: none;
    padding: 0px;
}

/* Line Edits & Spin Boxes */
QLineEdit, QSpinBox {
    background-color: #111214;
    border: 1px solid #3f4147;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f2f3f5;
    selection-background-color: #0284c7;
}

QLineEdit:focus, QSpinBox:focus {
    border-color: #38bdf8;
}

/* Tables */
QTableWidget {
    background-color: #111214;
    border: 1px solid #313338;
    border-radius: 6px;
    gridline-color: #232529;
    color: #e0e2e8;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    outline: 0;
}

QTableWidget::item:selected {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: bold;
}

QTableWidget::item:focus {
    background-color: #0284c7;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #2b2d31;
    color: #949ba4;
    padding: 8px;
    border: none;
    border-right: 1px solid #1e1f22;
    font-weight: 600;
}

QTableWidget::item {
    padding: 6px;
}

/* List Widgets */
QListWidget {
    background-color: #111214;
    border: 1px solid #313338;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #313338;
    border-radius: 6px;
    background-color: #111214;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #0ea5e9;
    border-radius: 5px;
}

/* Scroll Bars */
QScrollBar:vertical {
    border: none;
    background: #1e1f22;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3f4147;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #5c5f66;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Check Boxes & Radio Buttons */
QCheckBox, QRadioButton {
    spacing: 8px;
    color: #e0e2e8;
    font-size: 13px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
}

QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {
    border: 2px solid #5c5f66;
    background: #111214;
    border-radius: 4px;
}

QCheckBox::indicator:checked {
    border: 2px solid #0284c7;
    background: #0284c7;
    border-radius: 4px;
}

QRadioButton::indicator:unchecked {
    border-radius: 9px;
}

QRadioButton::indicator:checked {
    border: 2px solid #0284c7;
    background: #0284c7;
    border-radius: 9px;
}
"""
