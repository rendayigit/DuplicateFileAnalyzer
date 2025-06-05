"""
Professional Duplicate File Finder GUI
A modern PySide6 application for finding duplicate files with advanced features.
Author: @rendayigit
"""

import os
import sys
import json
import csv
import hashlib
import time
from collections import defaultdict
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QGroupBox,
    QCheckBox,
    QSpinBox,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QMenu,
    QStatusBar,
    QToolBar,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QSettings, QSize, QRect
from PySide6.QtGui import (
    QColor,
    QPalette,
    QAction,
    QKeySequence,
    QPainter,
    QBrush,
    QLinearGradient,
)


@dataclass
class ScanResult:
    """Data class for scan results"""

    total_files: int = 0
    total_size: int = 0
    duplicate_groups: int = 0
    duplicate_files: int = 0
    wasted_space: int = 0
    scan_time: float = 0.0
    directory: str = ""
    timestamp: str = ""


class DuplicateFinderCore(QObject):
    """Core duplicate finding logic as a QObject for threading"""

    # Signals for GUI updates
    progress_updated = Signal(int, str)
    stage_changed = Signal(str)
    scan_completed = Signal(dict)
    error_occurred = Signal(str)
    file_processed = Signal(str, int)

    def __init__(self, chunk_size=8192, quick_hash_size=1024):
        super().__init__()
        self.chunk_size = chunk_size
        self.quick_hash_size = quick_hash_size
        self.should_stop = False

    def stop_scan(self):
        """Stop the current scan"""
        self.should_stop = True

    def scan_directory(self, directory: str, file_filters: Optional[List[str]] = None):
        """Main scanning method"""
        try:
            self.should_stop = False
            start_time = time.time()

            # Stage 1: File discovery and size grouping
            self.stage_changed.emit("Discovering files...")
            size_groups = self._discover_files(directory, file_filters)

            if self.should_stop:
                return

            # Stage 2: Quick hash analysis
            self.stage_changed.emit("Performing quick analysis...")
            quick_hash_groups = self._quick_hash_analysis(size_groups)

            if self.should_stop:
                return

            # Stage 3: Full hash analysis
            self.stage_changed.emit("Performing deep analysis...")
            duplicate_groups = self._full_hash_analysis(quick_hash_groups)

            if self.should_stop:
                return

            # Calculate results
            scan_time = time.time() - start_time
            results = self._calculate_results(duplicate_groups, scan_time, directory)

            self.scan_completed.emit(results)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def _discover_files(
        self, directory: str, file_filters: Optional[List[str]] = None
    ) -> Dict[int, List[str]]:
        """Discover files and group by size"""
        size_groups = defaultdict(list)
        file_count = 0

        for root, dirs, files in os.walk(directory):
            if self.should_stop:
                break

            for file in files:
                if self.should_stop:
                    break

                filepath = os.path.join(root, file)

                # Apply file filters
                if file_filters and not any(
                    filepath.lower().endswith(ext.lower()) for ext in file_filters
                ):
                    continue

                if os.path.islink(filepath) or not os.path.isfile(filepath):
                    continue

                try:
                    file_size = os.path.getsize(filepath)
                    if file_size > 0:
                        size_groups[file_size].append(filepath)
                        file_count += 1

                        if file_count % 100 == 0:
                            self.file_processed.emit(filepath, file_count)
                            self.progress_updated.emit(
                                0, f"Discovered {file_count:,} files"
                            )

                except (OSError, IOError):
                    continue

        # Remove single-file groups
        return {size: files for size, files in size_groups.items() if len(files) > 1}

    def _quick_hash_analysis(
        self, size_groups: Dict[int, List[str]]
    ) -> Dict[str, List[str]]:
        """Quick hash analysis"""
        quick_hash_groups = defaultdict(list)
        total_files = sum(len(files) for files in size_groups.values())
        processed = 0

        for size, filepaths in size_groups.items():
            if self.should_stop:
                break

            for filepath in filepaths:
                if self.should_stop:
                    break

                quick_hash = self._get_quick_hash(filepath)
                if quick_hash:
                    key = f"{size}:{quick_hash}"
                    quick_hash_groups[key].append(filepath)

                processed += 1
                if total_files > 0:
                    progress = int((processed / total_files) * 100)
                    self.progress_updated.emit(
                        progress, f"Quick analysis: {processed:,}/{total_files:,}"
                    )

        return {
            key: files for key, files in quick_hash_groups.items() if len(files) > 1
        }

    def _full_hash_analysis(
        self, quick_hash_groups: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """Full hash analysis"""
        full_hash_groups = defaultdict(list)
        total_files = sum(len(files) for files in quick_hash_groups.values())
        processed = 0

        for key, filepaths in quick_hash_groups.items():
            if self.should_stop:
                break

            for filepath in filepaths:
                if self.should_stop:
                    break

                full_hash = self._get_full_hash(filepath)
                if full_hash:
                    full_hash_groups[full_hash].append(filepath)

                processed += 1
                if total_files > 0:
                    progress = int((processed / total_files) * 100)
                    self.progress_updated.emit(
                        progress, f"Deep analysis: {processed:,}/{total_files:,}"
                    )

        return {
            hash_val: files
            for hash_val, files in full_hash_groups.items()
            if len(files) > 1
        }

    def _get_quick_hash(self, filepath: str) -> str:
        """Get quick hash of file"""
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(self.quick_hash_size)
                return hashlib.md5(chunk).hexdigest()
        except (OSError, IOError):
            return ""

    def _get_full_hash(self, filepath: str) -> str:
        """Get full hash of file"""
        hash_obj = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except (OSError, IOError):
            return ""

    def _calculate_results(
        self, duplicate_groups: Dict[str, List[str]], scan_time: float, directory: str
    ) -> dict:
        """Calculate scan results"""
        total_duplicates = sum(len(files) - 1 for files in duplicate_groups.values())
        total_wasted = 0

        for files in duplicate_groups.values():
            if files:
                try:
                    file_size = os.path.getsize(files[0])
                    total_wasted += file_size * (len(files) - 1)
                except (OSError, IOError):
                    continue

        return {
            "groups": duplicate_groups,
            "total_groups": len(duplicate_groups),
            "total_duplicates": total_duplicates,
            "wasted_space": total_wasted,
            "scan_time": scan_time,
            "directory": directory,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class ScanWorker(QThread):
    """Worker thread for scanning"""

    def __init__(
        self,
        core: DuplicateFinderCore,
        directory: str,
        file_filters: Optional[List[str]] = None,
    ):
        super().__init__()
        self.core = core
        self.directory = directory
        self.file_filters = file_filters

    def run(self):
        """Run the scan in a separate thread"""
        self.core.scan_directory(self.directory, self.file_filters)


class ModernProgressBar(QWidget):
    """Custom modern progress bar with theme support"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.progress = 0
        self.text = ""
        self.is_dark = self.detect_dark_theme()

    def detect_dark_theme(self):
        """Detect dark theme for progress bar"""
        palette = QApplication.palette()
        bg_color = palette.color(QPalette.ColorRole.Window)
        return bg_color.lightness() < 128

    def set_progress(self, value: int, text: str = ""):
        """Set progress value and text"""
        self.progress = max(0, min(100, value))
        self.text = text
        self.update()

    def paintEvent(self, event):
        """Custom paint event with theme support"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background colors based on theme
        if self.is_dark:
            bg_color = QColor(60, 60, 60)
            text_color = QColor(255, 255, 255)
        else:
            bg_color = QColor(240, 240, 240)
            text_color = QColor(60, 60, 60)

        # Background
        bg_rect = self.rect()
        painter.fillRect(bg_rect, bg_color)

        # Progress
        if self.progress > 0:
            progress_width = int((self.progress / 100) * self.width())
            progress_rect = QRect(0, 0, progress_width, self.height())

            gradient = QLinearGradient(0, 0, progress_width, 0)
            if self.is_dark:
                gradient.setColorAt(0, QColor(0, 120, 212))  # Microsoft blue for dark
                gradient.setColorAt(1, QColor(16, 110, 190))
            else:
                gradient.setColorAt(0, QColor(74, 144, 226))  # Original light colors
                gradient.setColorAt(1, QColor(80, 200, 120))

            painter.fillRect(progress_rect, QBrush(gradient))

        # Text
        if self.text:
            painter.setPen(text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)


class SettingsDialog(QDialog):
    """Settings dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setFixedSize(400, 300)

        layout = QVBoxLayout(self)

        # Performance settings
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)

        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(1024, 1048576)
        self.chunk_size_spin.setValue(8192)
        self.chunk_size_spin.setSuffix(" bytes")
        perf_layout.addRow("Chunk Size:", self.chunk_size_spin)

        self.quick_hash_spin = QSpinBox()
        self.quick_hash_spin.setRange(512, 65536)
        self.quick_hash_spin.setValue(1024)
        self.quick_hash_spin.setSuffix(" bytes")
        perf_layout.addRow("Quick Hash Size:", self.quick_hash_spin)

        # UI settings
        ui_group = QGroupBox("Interface Settings")
        ui_layout = QFormLayout(ui_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "Auto"])
        ui_layout.addRow("Theme:", self.theme_combo)

        self.auto_save_check = QCheckBox("Auto-save results")
        ui_layout.addRow(self.auto_save_check)

        layout.addWidget(perf_group)
        layout.addWidget(ui_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DuplicateFileAnalyzer(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.settings = QSettings("DuplicateFinder", "Pro")
        self.scan_results = {}
        self.current_scan = None
        self.scan_worker = None
        self.is_dark_theme = self.detect_dark_theme()

        self.init_ui()
        self.load_settings()
        self.apply_modern_style()

    def _safe_int_setting(self, key: str, default: int) -> int:
        """Safely convert settings value to int"""
        value = self.settings.value(key, default)
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def _safe_str_setting(self, key: str, default: str) -> str:
        """Safely convert settings value to str"""
        value = self.settings.value(key, default)
        return str(value) if value is not None else default

    def _safe_bool_setting(self, key: str, default: bool) -> bool:
        """Safely convert settings value to bool"""
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return default

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Duplicate File Analyzer Pro")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top toolbar
        self.create_toolbar()

        # Main content
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        left_panel = self.create_left_panel()
        main_splitter.addWidget(left_panel)

        # Right panel (results)
        right_panel = self.create_right_panel()
        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([400, 800])
        main_layout.addWidget(main_splitter)

        # Status bar
        self.create_status_bar()

        # Menu bar
        self.create_menu_bar()

    def create_toolbar(self):
        """Create the main toolbar"""
        toolbar = QToolBar()
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(32, 32))

        # Scan action - Fixed QAction constructor
        scan_action = QAction("Start Scan", self)
        scan_action.setToolTip("Start Scan")
        scan_action.setShortcut(QKeySequence.StandardKey.New)
        scan_action.triggered.connect(self.start_scan)
        toolbar.addAction(scan_action)

        # Stop action
        self.stop_action = QAction("Stop Scan", self)
        self.stop_action.setToolTip("Stop Scan")
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self.stop_scan)
        toolbar.addAction(self.stop_action)

        toolbar.addSeparator()

        # Export action
        export_action = QAction("Export Results", self)
        export_action.setToolTip("Export Results")
        export_action.triggered.connect(self.export_results)
        toolbar.addAction(export_action)

        # Settings action
        settings_action = QAction("Settings", self)
        settings_action.setToolTip("Settings")
        settings_action.triggered.connect(self.show_settings)
        toolbar.addAction(settings_action)

        self.addToolBar(toolbar)

    def detect_dark_theme(self):
        """Detect if system is using dark theme"""
        # Check system theme preference
        palette = QApplication.palette()
        bg_color = palette.color(QPalette.ColorRole.Window)

        # If background is darker than middle gray, assume dark theme
        return bg_color.lightness() < 128

    def create_left_panel(self):
        """Create the left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Directory selection
        dir_group = QGroupBox("Scan Directory")
        dir_layout = QVBoxLayout(dir_group)

        dir_input_layout = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("Select directory to scan...")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_directory)

        dir_input_layout.addWidget(self.directory_edit)
        dir_input_layout.addWidget(browse_btn)
        dir_layout.addLayout(dir_input_layout)

        # File filters
        filter_group = QGroupBox("File Filters")
        filter_layout = QVBoxLayout(filter_group)

        self.filter_all = QCheckBox("All Files")
        self.filter_all.setChecked(True)
        self.filter_all.toggled.connect(self.on_filter_all_toggled)
        filter_layout.addWidget(self.filter_all)

        # Common file type filters
        self.filter_images = QCheckBox("Images (.jpg, .png, .gif, etc.)")
        self.filter_videos = QCheckBox("Videos (.mp4, .avi, .mkv, etc.)")
        self.filter_audio = QCheckBox("Audio (.mp3, .wav, .flac, etc.)")
        self.filter_documents = QCheckBox("Documents (.pdf, .doc, .txt, etc.)")
        self.filter_archives = QCheckBox("Archives (.zip, .rar, .7z, etc.)")

        for checkbox in [
            self.filter_images,
            self.filter_videos,
            self.filter_audio,
            self.filter_documents,
            self.filter_archives,
        ]:
            filter_layout.addWidget(checkbox)

        # Progress section
        progress_group = QGroupBox("Scan Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = ModernProgressBar()
        self.stage_label = QLabel("Ready to scan")
        self.stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress_bar)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout(stats_group)

        self.stats_labels = {
            "files": QLabel("0"),
            "groups": QLabel("0"),
            "duplicates": QLabel("0"),
            "wasted": QLabel("0 B"),
            "time": QLabel("0.0s"),
        }

        stats_layout.addWidget(QLabel("Files Scanned:"), 0, 0)
        stats_layout.addWidget(self.stats_labels["files"], 0, 1)
        stats_layout.addWidget(QLabel("Duplicate Groups:"), 1, 0)
        stats_layout.addWidget(self.stats_labels["groups"], 1, 1)
        stats_layout.addWidget(QLabel("Duplicate Files:"), 2, 0)
        stats_layout.addWidget(self.stats_labels["duplicates"], 2, 1)
        stats_layout.addWidget(QLabel("Wasted Space:"), 3, 0)
        stats_layout.addWidget(self.stats_labels["wasted"], 3, 1)
        stats_layout.addWidget(QLabel("Scan Time:"), 4, 0)
        stats_layout.addWidget(self.stats_labels["time"], 4, 1)

        # Add all groups to panel
        layout.addWidget(dir_group)
        layout.addWidget(filter_group)
        layout.addWidget(progress_group)
        layout.addWidget(stats_group)
        layout.addStretch()

        return panel

    def create_right_panel(self):
        """Create the right results panel"""
        self.results_tab_widget = QTabWidget()

        # Results tree tab
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["File", "Size", "Path"])
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(self.show_context_menu)
        self.results_tab_widget.addTab(self.results_tree, "Duplicate Groups")

        # Details tab
        self.details_table = QTableWidget()
        self.details_table.setColumnCount(4)
        self.details_table.setHorizontalHeaderLabels(
            ["Property", "Value", "Original", "Duplicate"]
        )
        self.results_tab_widget.addTab(self.details_table, "File Details")

        # History tab
        self.history_list = QListWidget()
        self.results_tab_widget.addTab(self.history_list, "Scan History")

        return self.results_tab_widget

    def create_status_bar(self):
        """Create the status bar"""
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

    def create_menu_bar(self):
        """Create the menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        new_scan_action = QAction("New Scan", self)
        new_scan_action.setShortcut(QKeySequence.StandardKey.New)
        new_scan_action.triggered.connect(self.start_scan)
        file_menu.addAction(new_scan_action)

        file_menu.addSeparator()

        export_action = QAction("Export Results", self)
        export_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def apply_modern_style(self):
        """Apply modern styling with theme support"""
        if self.is_dark_theme:
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

    def apply_dark_theme(self):
        """Apply dark theme styling"""
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #3c3c3c;
                color: #ffffff;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ffffff;
            }
            
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #106ebe;
            }
            
            QPushButton:pressed {
                background-color: #005a9e;
            }
            
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #888888;
            }
            
            QLineEdit {
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
                background-color: #3c3c3c;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border-color: #0078d4;
            }
            
            QTreeWidget {
                border: 1px solid #555555;
                border-radius: 6px;
                background-color: #3c3c3c;
                color: #ffffff;
                alternate-background-color: #404040;
            }
            
            QTreeWidget::item {
                padding: 4px;
                border: none;
            }
            
            QTreeWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            
            QTreeWidget::item:hover {
                background-color: #404040;
            }
            
            QTreeWidget QHeaderView::section {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 8px;
                border: 1px solid #555555;
            }
            
            QTabWidget::pane {
                border: 1px solid #555555;
                border-radius: 6px;
                background-color: #3c3c3c;
            }
            
            QTabBar::tab {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            
            QTabBar::tab:selected {
                background-color: #0078d4;
                color: white;
            }
            
            QTabBar::tab:hover {
                background-color: #555555;
            }
            
            QCheckBox {
                spacing: 8px;
                color: #ffffff;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #555555;
                background-color: #3c3c3c;
            }
            
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            
            QCheckBox::indicator:hover {
                border-color: #777777;
            }
            
            QLabel {
                color: #ffffff;
            }
            
            QTableWidget {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                gridline-color: #555555;
            }
            
            QTableWidget QHeaderView::section {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 8px;
                border: 1px solid #555555;
            }
            
            QListWidget {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 6px;
            }
            
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #555555;
            }
            
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            
            QListWidget::item:hover {
                background-color: #404040;
            }
            
            QMenuBar {
                background-color: #4a4a4a;
                color: #ffffff;
                border-bottom: 1px solid #555555;
            }
            
            QMenuBar::item:selected {
                background-color: #0078d4;
            }
            
            QMenu {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
            }
            
            QMenu::item:selected {
                background-color: #0078d4;
            }
            
            QStatusBar {
                background-color: #4a4a4a;
                color: #ffffff;
                border-top: 1px solid #555555;
            }
            
            QToolBar {
                background-color: #4a4a4a;
                border: 1px solid #555555;
                spacing: 2px;
            }
            
            QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 6px;
            }
            
            QComboBox:hover {
                border-color: #777777;
            }
            
            QComboBox::drop-down {
                border: none;
            }
            
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
            }
            
            QSpinBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 6px;
            }
            
            QSpinBox:hover {
                border-color: #777777;
            }
        """
        )

    def apply_light_theme(self):
        """Apply light theme styling (original)"""
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f8f9fa;
                color: #212529;
            }
            
            QWidget {
                background-color: #f8f9fa;
                color: #212529;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
                color: #495057;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #495057;
            }
            
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #0056b3;
            }
            
            QPushButton:pressed {
                background-color: #004085;
            }
            
            QPushButton:disabled {
                background-color: #6c757d;
                color: #ffffff;
            }
            
            QLineEdit {
                border: 2px solid #ced4da;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
                background-color: white;
                color: #495057;
            }
            
            QLineEdit:focus {
                border-color: #007bff;
            }
            
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
                color: #495057;
                alternate-background-color: #f8f9fa;
            }
            
            QTreeWidget::item {
                padding: 4px;
                border: none;
            }
            
            QTreeWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            
            QTreeWidget::item:hover {
                background-color: #e9ecef;
            }
            
            QTreeWidget QHeaderView::section {
                background-color: #e9ecef;
                color: #495057;
                padding: 8px;
                border: 1px solid #dee2e6;
            }
            
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #e9ecef;
                color: #495057;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            
            QTabBar::tab:selected {
                background-color: #007bff;
                color: white;
            }
            
            QTabBar::tab:hover {
                background-color: #f8f9fa;
            }
            
            QCheckBox {
                spacing: 8px;
                color: #495057;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #ced4da;
                background-color: white;
            }
            
            QCheckBox::indicator:checked {
                background-color: #007bff;
                border-color: #007bff;
            }
            
            QCheckBox::indicator:hover {
                border-color: #adb5bd;
            }
            
            QLabel {
                color: #495057;
            }
            
            QTableWidget {
                background-color: white;
                color: #495057;
                border: 1px solid #dee2e6;
                gridline-color: #dee2e6;
            }
            
            QTableWidget QHeaderView::section {
                background-color: #e9ecef;
                color: #495057;
                padding: 8px;
                border: 1px solid #dee2e6;
            }
            
            QListWidget {
                background-color: white;
                color: #495057;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #dee2e6;
            }
            
            QListWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            
            QListWidget::item:hover {
                background-color: #f8f9fa;
            }
            
            QMenuBar {
                background-color: #e9ecef;
                color: #495057;
                border-bottom: 1px solid #dee2e6;
            }
            
            QMenuBar::item:selected {
                background-color: #007bff;
                color: white;
            }
            
            QMenu {
                background-color: white;
                color: #495057;
                border: 1px solid #dee2e6;
            }
            
            QMenu::item:selected {
                background-color: #007bff;
                color: white;
            }
            
            QStatusBar {
                background-color: #e9ecef;
                color: #495057;
                border-top: 1px solid #dee2e6;
            }
            
            QToolBar {
                background-color: #e9ecef;
                border: 1px solid #dee2e6;
                spacing: 2px;
            }
            
            QComboBox {
                background-color: white;
                color: #495057;
                border: 2px solid #ced4da;
                border-radius: 6px;
                padding: 6px;
            }
            
            QComboBox:hover {
                border-color: #adb5bd;
            }
            
            QComboBox::drop-down {
                border: none;
            }
            
            QComboBox QAbstractItemView {
                background-color: white;
                color: #495057;
                border: 1px solid #dee2e6;
            }
            
            QSpinBox {
                background-color: white;
                color: #495057;
                border: 2px solid #ced4da;
                border-radius: 6px;
                padding: 6px;
            }
            
            QSpinBox:hover {
                border-color: #adb5bd;
            }
        """
        )

    def browse_directory(self):
        """Browse for directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Scan",
            self.directory_edit.text() or os.path.expanduser("~"),
        )
        if directory:
            self.directory_edit.setText(directory)

    def on_filter_all_toggled(self, checked):
        """Handle 'All Files' filter toggle"""
        if checked:
            for checkbox in [
                self.filter_images,
                self.filter_videos,
                self.filter_audio,
                self.filter_documents,
                self.filter_archives,
            ]:
                checkbox.setChecked(False)

    def get_file_filters(self):
        """Get selected file filters"""
        if self.filter_all.isChecked():
            return None

        filters = []
        if self.filter_images.isChecked():
            filters.extend([".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"])
        if self.filter_videos.isChecked():
            filters.extend([".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"])
        if self.filter_audio.isChecked():
            filters.extend([".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"])
        if self.filter_documents.isChecked():
            filters.extend([".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"])
        if self.filter_archives.isChecked():
            filters.extend([".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"])

        return filters if filters else None

    def start_scan(self):
        """Start the duplicate scan"""
        directory = self.directory_edit.text().strip()
        if not directory:
            QMessageBox.warning(self, "Warning", "Please select a directory to scan.")
            return

        if not os.path.isdir(directory):
            QMessageBox.warning(self, "Warning", "Selected directory does not exist.")
            return

        # Setup UI for scanning
        self.stop_action.setEnabled(True)
        self.progress_bar.set_progress(0, "Initializing scan...")
        self.stage_label.setText("Initializing...")

        # Clear previous results
        self.results_tree.clear()
        self.details_table.setRowCount(0)

        # Create core and worker with proper type conversion
        chunk_size = self._safe_int_setting("chunk_size", 8192)
        quick_hash_size = self._safe_int_setting("quick_hash_size", 1024)

        self.current_scan = DuplicateFinderCore(chunk_size, quick_hash_size)
        self.current_scan.progress_updated.connect(self.update_progress)
        self.current_scan.stage_changed.connect(self.update_stage)
        self.current_scan.scan_completed.connect(self.scan_completed)
        self.current_scan.error_occurred.connect(self.scan_error)

        file_filters = self.get_file_filters()
        self.scan_worker = ScanWorker(self.current_scan, directory, file_filters)
        self.scan_worker.finished.connect(self.scan_finished)
        self.scan_worker.start()

    def stop_scan(self):
        """Stop the current scan"""
        if self.current_scan:
            self.current_scan.stop_scan()
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.quit()
            self.scan_worker.wait()

        self.stop_action.setEnabled(False)
        self.stage_label.setText("Scan stopped")
        self.status_bar.showMessage("Scan stopped by user")

    def update_progress(self, value: int, text: str):
        """Update progress bar"""
        self.progress_bar.set_progress(value, text)
        self.status_bar.showMessage(text)

    def update_stage(self, stage: str):
        """Update current stage"""
        self.stage_label.setText(stage)

    def scan_completed(self, results: dict):
        """Handle scan completion"""
        self.scan_results = results
        self.populate_results_tree(results["groups"])
        self.update_statistics(results)
        self.add_to_history(results)

        self.stage_label.setText("Scan completed")
        self.status_bar.showMessage(
            f"Scan completed - Found {results['total_groups']} duplicate groups"
        )

    def scan_error(self, error: str):
        """Handle scan error"""
        QMessageBox.critical(
            self, "Scan Error", f"An error occurred during scanning:\n{error}"
        )
        self.stage_label.setText("Scan failed")
        self.status_bar.showMessage("Scan failed")

    def scan_finished(self):
        """Handle scan worker finished"""
        self.stop_action.setEnabled(False)

    def populate_results_tree(self, duplicate_groups: dict):
        """Populate the results tree with duplicate groups"""
        self.results_tree.clear()

        for i, (hash_val, files) in enumerate(duplicate_groups.items(), 1):
            if not files:
                continue

            # Create group item
            try:
                file_size = os.path.getsize(files[0])
                wasted_space = file_size * (len(files) - 1)

                group_item = QTreeWidgetItem(
                    [
                        f"Group {i} ({len(files)} files)",
                        self.format_size(wasted_space) + " wasted",
                        f"{len(files)} duplicates",
                    ]
                )
                group_item.setData(0, Qt.ItemDataRole.UserRole, hash_val)

                # Add individual files
                for j, filepath in enumerate(files):
                    file_item = QTreeWidgetItem(
                        [
                            os.path.basename(filepath),
                            self.format_size(file_size),
                            filepath,
                        ]
                    )
                    file_item.setData(0, Qt.ItemDataRole.UserRole, filepath)

                    # Mark first as original
                    if j == 0:
                        file_item.setText(0, f"📍 {file_item.text(0)}")
                    else:
                        file_item.setText(0, f"🔄 {file_item.text(0)}")

                    group_item.addChild(file_item)

                self.results_tree.addTopLevelItem(group_item)
                group_item.setExpanded(True)

            except (OSError, IOError):
                continue

    def update_statistics(self, results: dict):
        """Update statistics display"""
        total_files = sum(len(files) for files in results["groups"].values())

        self.stats_labels["files"].setText(f"{total_files:,}")
        self.stats_labels["groups"].setText(f"{results['total_groups']:,}")
        self.stats_labels["duplicates"].setText(f"{results['total_duplicates']:,}")
        self.stats_labels["wasted"].setText(self.format_size(results["wasted_space"]))
        self.stats_labels["time"].setText(f"{results['scan_time']:.1f}s")

    def add_to_history(self, results: dict):
        """Add scan to history"""
        timestamp = results["timestamp"]
        directory = results["directory"]
        groups = results["total_groups"]

        history_text = f"{timestamp} - {directory} ({groups} groups)"
        item = QListWidgetItem(history_text)
        item.setData(Qt.ItemDataRole.UserRole, results)
        self.history_list.addItem(item)

    def show_context_menu(self, position):
        """Show context menu for results tree"""
        item = self.results_tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        if item.parent():  # File item
            filepath = item.data(0, Qt.ItemDataRole.UserRole)
            if filepath and os.path.isfile(filepath):
                open_action = menu.addAction("Open File")
                open_action.triggered.connect(lambda: self.open_file(filepath))

                show_action = menu.addAction("Show in Explorer")
                show_action.triggered.connect(lambda: self.show_in_explorer(filepath))

                menu.addSeparator()

                delete_action = menu.addAction("Delete File")
                delete_action.triggered.connect(lambda: self.delete_file(filepath))

        menu.exec_(self.results_tree.mapToGlobal(position))

    def open_file(self, filepath: str):
        """Open file with default application"""
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
            elif sys.platform == "darwin":
                os.system(f'open "{filepath}"')
            else:
                os.system(f'xdg-open "{filepath}"')
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not open file:\n{str(e)}")

    def show_in_explorer(self, filepath: str):
        """Show file in system explorer"""
        try:
            if sys.platform == "win32":
                os.startfile(os.path.dirname(filepath))
            elif sys.platform == "darwin":
                os.system(f'open "{os.path.dirname(filepath)}"')
            else:
                os.system(f'xdg-open "{os.path.dirname(filepath)}"')
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not open directory:\n{str(e)}")

    def delete_file(self, filepath: str):
        """Delete a file after confirmation"""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this file?\n\n{filepath}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(filepath)
                QMessageBox.information(self, "Success", "File deleted successfully.")
                # Refresh the current scan results
                if self.scan_results:
                    self.populate_results_tree(self.scan_results["groups"])
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete file:\n{str(e)}")

    def export_results(self):
        """Export scan results"""
        if not self.scan_results:
            QMessageBox.warning(self, "Warning", "No scan results to export.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            f"duplicate_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON files (*.json);;Text files (*.txt);;CSV files (*.csv)",
        )

        if filename:
            try:
                if filename.endswith(".json"):
                    self.export_json(filename)
                elif filename.endswith(".csv"):
                    self.export_csv(filename)
                else:
                    self.export_text(filename)

                QMessageBox.information(
                    self, "Success", f"Results exported to:\n{filename}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to export results:\n{str(e)}"
                )

    def export_json(self, filename: str):
        """Export results as JSON"""
        export_data = {
            "scan_info": {
                "directory": self.scan_results["directory"],
                "timestamp": self.scan_results["timestamp"],
                "scan_time": self.scan_results["scan_time"],
                "total_groups": self.scan_results["total_groups"],
                "total_duplicates": self.scan_results["total_duplicates"],
                "wasted_space": self.scan_results["wasted_space"],
            },
            "duplicate_groups": self.scan_results["groups"],
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def export_csv(self, filename: str):
        """Export results as CSV"""
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Group", "Hash", "File Path", "File Size", "Is Duplicate"])

            for i, (hash_val, files) in enumerate(
                self.scan_results["groups"].items(), 1
            ):
                for j, filepath in enumerate(files):
                    try:
                        file_size = os.path.getsize(filepath)
                        writer.writerow([i, hash_val, filepath, file_size, j > 0])
                    except (OSError, IOError):
                        continue

    def export_text(self, filename: str):
        """Export results as text"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Duplicate File Analysis Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Directory: {self.scan_results['directory']}\n")
            f.write(f"Scan Date: {self.scan_results['timestamp']}\n")
            f.write(f"Scan Time: {self.scan_results['scan_time']:.2f} seconds\n")
            f.write(f"Duplicate Groups: {self.scan_results['total_groups']}\n")
            f.write(f"Duplicate Files: {self.scan_results['total_duplicates']}\n")
            f.write(
                f"Wasted Space: {self.format_size(self.scan_results['wasted_space'])}\n\n"
            )

            for i, (hash_val, files) in enumerate(
                self.scan_results["groups"].items(), 1
            ):
                if files:
                    try:
                        file_size = os.path.getsize(files[0])
                        wasted_space = file_size * (len(files) - 1)

                        f.write(f"Group {i}: {len(files)} files\n")
                        f.write(f"Size: {self.format_size(file_size)} each\n")
                        f.write(f"Wasted: {self.format_size(wasted_space)}\n")
                        f.write(f"Hash: {hash_val}\n")

                        for j, filepath in enumerate(files):
                            marker = "ORIGINAL" if j == 0 else "DUPLICATE"
                            f.write(f"  {marker}: {filepath}\n")
                        f.write("\n")
                    except (OSError, IOError):
                        continue

    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)

        # Load current settings with proper type conversion
        dialog.chunk_size_spin.setValue(self._safe_int_setting("chunk_size", 8192))
        dialog.quick_hash_spin.setValue(self._safe_int_setting("quick_hash_size", 1024))
        dialog.theme_combo.setCurrentText(self._safe_str_setting("theme", "Auto"))
        dialog.auto_save_check.setChecked(self._safe_bool_setting("auto_save", False))

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save settings
            self.settings.setValue("chunk_size", dialog.chunk_size_spin.value())
            self.settings.setValue("quick_hash_size", dialog.quick_hash_spin.value())
            self.settings.setValue("theme", dialog.theme_combo.currentText())
            self.settings.setValue("auto_save", dialog.auto_save_check.isChecked())

            # Apply theme changes immediately
            theme_setting = dialog.theme_combo.currentText()
            if theme_setting == "Auto":
                self.is_dark_theme = self.detect_dark_theme()
            elif theme_setting == "Dark":
                self.is_dark_theme = True
            else:
                self.is_dark_theme = False

            self.apply_modern_style()
            # Also update progress bar theme
            self.progress_bar.is_dark = self.is_dark_theme
            self.progress_bar.update()

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Duplicate File Analyzer Pro",
            """
            <h3>Duplicate File Analyzer Pro</h3>
            <p><b>Version:</b> 1.0.0</p>
            <p><b>Author:</b> @rendayigit</p>
            
            <p>A professional duplicate file finder with advanced features:</p>
            <ul>
            <li>Fast multi-stage analysis</li>
            <li>Modern GUI interface</li>
            <li>Multiple export formats</li>
            <li>File type filtering</li>
            <li>Scan history</li>
            </ul>
            
            <p>Built with PySide6 and Python.</p>
            """,
        )

    def load_settings(self):
        """Load application settings"""
        # Load geometry and window state with proper type handling
        geometry = self.settings.value("geometry", b"")
        if isinstance(geometry, bytes) and geometry:
            self.restoreGeometry(geometry)

        window_state = self.settings.value("windowState", b"")
        if isinstance(window_state, bytes) and window_state:
            self.restoreState(window_state)

        # Load last directory with type checking
        last_dir = self._safe_str_setting("last_directory", "")
        if last_dir and os.path.isdir(last_dir):
            self.directory_edit.setText(last_dir)

        # Load theme setting and apply
        theme_setting = self._safe_str_setting("theme", "Auto")
        if theme_setting == "Auto":
            self.is_dark_theme = self.detect_dark_theme()
        elif theme_setting == "Dark":
            self.is_dark_theme = True
        else:
            self.is_dark_theme = False

    def save_settings(self):
        """Save application settings"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("last_directory", self.directory_edit.text())

    def closeEvent(self, event):
        """Handle application close"""
        if self.scan_worker and self.scan_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A scan is currently running. Do you want to stop it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.stop_scan()
            else:
                event.ignore()
                return

        self.save_settings()
        event.accept()

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes as human readable string"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
        i = 0
        size = float(size_bytes)

        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.1f} {size_names[i]}"


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Duplicate File Analyzer Pro")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DuplicateFinder")
    app.setOrganizationDomain("github.com/rendayigit")

    # Set application icon (you can add an icon file)
    # app.setWindowIcon(QIcon("icon.png"))

    window = DuplicateFileAnalyzer()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
