import sys
import os
import threading
import queue
import time
import pandas as pd
from PyQt5 import QtWidgets, QtGui, QtCore
import fetcher_core
import downloader_core
import webbrowser

# --- Spotify integration ---
import requests
import base64

# Fill in your Spotify app credentials here (for public playlist access):
CLIENT_ID = 'YOUR_SPOTIFY_CLIENT_ID'
CLIENT_SECRET = 'YOUR_SPOTIFY_CLIENT_SECRET'

SPOTIFY_API_BASE = 'https://api.spotify.com/v1'
SPOTIFY_PUBLIC_TOKEN = 'BQD0'  # Placeholder, not needed for public playlists

class SegmentedControl(QtWidgets.QWidget):
    modeChanged = QtCore.pyqtSignal(int)
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.buttons = []
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        for i, label in enumerate(labels):
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setMinimumWidth(120)
            btn.setStyleSheet(self._button_style(i, len(labels)))
            btn.clicked.connect(lambda checked, idx=i: self.modeChanged.emit(idx))
            self.buttons.append(btn)
            layout.addWidget(btn)
        self.set_mode(0)
    def set_mode(self, idx):
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == idx)
    def _button_style(self, idx, total):
        radius = 10
        if idx == 0:
            return f"""
                QPushButton {{ border-top-left-radius: {radius}px; border-bottom-left-radius: {radius}px; border-right: none; }}
                QPushButton:checked {{ background: #4CAF50; color: white; }}
            """
        elif idx == total - 1:
            return f"""
                QPushButton {{ border-top-right-radius: {radius}px; border-bottom-right-radius: {radius}px; border-left: none; }}
                QPushButton:checked {{ background: #4CAF50; color: white; }}
            """
        else:
            return """
                QPushButton { border-radius: 0px; border-left: none; border-right: none; }
                QPushButton:checked { background: #4CAF50; color: white; }
            """

class Worker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(dict)
    def __init__(self, input_csv, output_csv, failed_csv, pause_event, stop_event, download_audio=False, download_dir=None, thread_count=1, audio_format='opus'):
        super().__init__()
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.failed_csv = failed_csv
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.download_audio = download_audio
        self.download_dir = download_dir
        self.thread_count = thread_count
        self.audio_format = audio_format
    def run(self):
        try:
            df = pd.read_csv(self.input_csv)
        except Exception as e:
            self.progress_signal.emit({'type': 'error', 'msg': f'Error reading input CSV: {e}'})
            return
        cols = set(df.columns)
        def is_valid_yt(url):
            s = str(url)
            return s.startswith('http') and 'youtube' in s.lower()

        if {'Artist Name(s)', 'Track Name'}.issubset(cols):
            if 'url' in cols:
                to_fetch = df[(df['url'].isna()) | (df['url'] == 'FAILED') | (~df['url'].apply(is_valid_yt))]
                already_present = len(df) - len(to_fetch)
                if len(to_fetch) == 0:
                    self.progress_signal.emit({'type': 'log', 'msg': f'All tracks already have YouTube links ({already_present} present). Skipping fetch.'})
                    if self.download_audio:
                        urls = [str(u) for u in df['url'] if is_valid_yt(u)]
                        self.progress_signal.emit({'type': 'log', 'msg': f'Starting audio download for {len(urls)} tracks...'})
                        downloader_core.download_audio(urls, self.download_dir, self.progress_signal.emit, self.pause_event, self.stop_event, self.thread_count, self.audio_format)
                    return
                else:
                    self.progress_signal.emit({'type': 'log', 'msg': f'Fetching {len(to_fetch)} missing YouTube links (using {self.thread_count} threads)...'})
                    temp_input = self.input_csv + '.tofetch.csv'
                    to_fetch.to_csv(temp_input, index=False)
                    fetcher_core.run_fetch(
                        temp_input,
                        self.output_csv,
                        self.failed_csv,
                        self.progress_signal.emit,
                        self.pause_event,
                        self.stop_event,
                        self.thread_count
                    )
                    if self.download_audio:
                        try:
                            links_df = pd.read_csv(self.output_csv)
                            urls = [str(u) for u in links_df['url'] if is_valid_yt(u)]
                        except Exception as e:
                            self.progress_signal.emit({'type': 'error', 'msg': f'Error reading output CSV: {e}'})
                            return
                        self.progress_signal.emit({'type': 'log', 'msg': f'Starting audio download for {len(urls)} tracks...'})
                        downloader_core.download_audio(urls, self.download_dir, self.progress_signal.emit, self.pause_event, self.stop_event, self.thread_count, self.audio_format)
                    return
            else:
                self.progress_signal.emit({'type': 'log', 'msg': f'Fetching YouTube links for all {len(df)} tracks (using {self.thread_count} threads)...'})
                fetcher_core.run_fetch(
                    self.input_csv,
                    self.output_csv,
                    self.failed_csv,
                    self.progress_signal.emit,
                    self.pause_event,
                    self.stop_event,
                    self.thread_count
                )
                if self.download_audio:
                    try:
                        links_df = pd.read_csv(self.output_csv)
                        urls = [str(u) for u in links_df['url'] if is_valid_yt(u)]
                    except Exception as e:
                        self.progress_signal.emit({'type': 'error', 'msg': f'Error reading output CSV: {e}'})
                        return
                    self.progress_signal.emit({'type': 'log', 'msg': f'Starting audio download for {len(urls)} tracks...'})
                    downloader_core.download_audio(urls, self.download_dir, self.progress_signal.emit, self.pause_event, self.stop_event, self.thread_count, self.audio_format)
        elif 'url' in cols:
            valid_urls = [str(u) for u in df['url'] if is_valid_yt(u)]
            if len(valid_urls) == 0:
                self.progress_signal.emit({'type': 'error', 'msg': 'No valid YouTube links found in input CSV.'})
                return
            self.progress_signal.emit({'type': 'log', 'msg': f'Starting audio download for {len(valid_urls)} tracks...'})
            downloader_core.download_audio(valid_urls, self.download_dir, self.progress_signal.emit, self.pause_event, self.stop_event, self.thread_count, self.audio_format)
        elif 'query' in cols:
            to_fetch = df[(df['url'].isna()) | (df['url'] == 'FAILED') | (~df['url'].apply(is_valid_yt))] if 'url' in cols else df
            already_present = len(df) - len(to_fetch)
            if len(to_fetch) == 0:
                self.progress_signal.emit({'type': 'log', 'msg': f'All failed links already have YouTube links ({already_present} present). Skipping fetch.'})
                return
            self.progress_signal.emit({'type': 'log', 'msg': f'Fetching {len(to_fetch)} failed/missing YouTube links (using {self.thread_count} threads)...'})
            temp_input = self.input_csv + '.tofetch.csv'
            to_fetch.to_csv(temp_input, index=False)
            fetcher_core.run_fetch(
                temp_input,
                self.output_csv,
                self.failed_csv,
                self.progress_signal.emit,
                self.pause_event,
                self.stop_event,
                self.thread_count
            )
            if self.download_audio:
                try:
                    links_df = pd.read_csv(self.output_csv)
                    urls = [str(u) for u in links_df['url'] if is_valid_yt(u)]
                except Exception as e:
                    self.progress_signal.emit({'type': 'error', 'msg': f'Error reading output CSV: {e}'})
                    return
                self.progress_signal.emit({'type': 'log', 'msg': f'Starting audio download for {len(urls)} tracks...'})
                downloader_core.download_audio(urls, self.download_dir, self.progress_signal.emit, self.pause_event, self.stop_event, self.thread_count, self.audio_format)
        else:
            self.progress_signal.emit({'type': 'error', 'msg': 'Unrecognized input CSV format.'})
            return

class SpotubeApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Spotube Fetch')
        self.setWindowIcon(QtGui.QIcon('logo.png'))
        self.setGeometry(100, 100, 800, 800)
        self.queue = queue.Queue()
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.worker = None
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self.total = 0
        self.thread_count = 1
        self.audio_format = 'opus'
        self._build_ui()
        self.setStyleSheet(self._main_stylesheet())

    def _main_stylesheet(self):
        return """
        QWidget {
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-size: 14pt;
            background: #181a1b;
            color: #f5f5f7;
        }
        QPushButton {
            background-color: #23272a;
            color: #f5f5f7;
            border: 1px solid #444;
            border-radius: 10px;
            padding: 10px 22px;
            font-size: 14pt;
        }
        QPushButton:checked {
            background-color: #4CAF50;
            color: white;
        }
        QPushButton:disabled {
            background-color: #333;
            color: #888;
        }
        QProgressBar {
            border: 1px solid #444;
            border-radius: 10px;
            text-align: center;
            font-size: 14pt;
            height: 32px;
            background: #23272a;
            color: #f5f5f7;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 10px;
        }
        QPlainTextEdit {
            background: #23272a;
            color: #f5f5f7;
            border-radius: 10px;
            font-family: 'Fira Mono', 'Consolas', 'Courier', monospace;
            font-size: 12pt;
            padding: 10px;
        }
        QLineEdit {
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 14pt;
            background: #23272a;
            color: #f5f5f7;
            border: 1px solid #444;
        }
        QLabel#sectionLabel {
            font-size: 16pt;
            font-weight: bold;
            color: #f5f5f7;
            margin-top: 18px;
        }
        QComboBox {
            font-size: 14pt;
            padding: 6px 12px;
            border-radius: 8px;
            background: #23272a;
            color: #f5f5f7;
            border: 1px solid #444;
        }
        QCheckBox {
            font-size: 13pt;
            color: #f5f5f7;
        }
        """

    def _build_ui(self):
        self.resize(900, 520)
        self.setStyleSheet('background-color: #202124;')
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setSpacing(12)
        outer_layout.setContentsMargins(32, 18, 32, 18)

        # Logo at the top, spanning both columns
        logo = QtWidgets.QLabel()
        pixmap = QtGui.QPixmap('logo.png')
        pixmap = pixmap.scaledToWidth(140, QtCore.Qt.SmoothTransformation)
        logo.setPixmap(pixmap)
        logo.setAlignment(QtCore.Qt.AlignHCenter)
        logo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        logo.setStyleSheet('background: transparent;')
        outer_layout.addWidget(logo)

        # Main horizontal layout (two columns)
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(18)
        outer_layout.addLayout(main_layout)

        groupbox_style = 'QGroupBox { border: 1.5px solid #333; border-radius: 12px; margin-top: 8px; background: #202124; }'
        label_style = 'font-size:13pt; color:#f5f5f7; background: transparent;'

        # Left column: Step 1 and Step 2
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(12)
        main_layout.addLayout(left_col, 1)

        # Step 1: Exportify instructions
        box1 = QtWidgets.QGroupBox()
        box1.setStyleSheet(groupbox_style)
        box1_layout = QtWidgets.QVBoxLayout(box1)
        box1_layout.setSpacing(8)
        box1_layout.setContentsMargins(18, 12, 18, 12)
        step1 = QtWidgets.QLabel('Step 1: Export Your Spotify Playlist with Exportify')
        step1.setObjectName('sectionLabel')
        step1.setAlignment(QtCore.Qt.AlignHCenter)
        step1.setStyleSheet(label_style)
        box1_layout.addWidget(step1)
        instructions = QtWidgets.QLabel(
            '1. <b>Click the button below to open Exportify in your browser.</b><br>'
            '2. Log in to Spotify if needed.<br>'
            '3. Click "Get Started", then "Export" next to your playlist.<br>'
            '4. Save the CSV file to your computer.<br>'
            '5. Return here and load the CSV below.'
        )
        instructions.setAlignment(QtCore.Qt.AlignHCenter)
        instructions.setWordWrap(True)
        instructions.setStyleSheet(label_style + ' margin-bottom:12px;')
        box1_layout.addWidget(instructions)
        exportify_btn = QtWidgets.QPushButton('Open Exportify')
        exportify_btn.setStyleSheet('font-size:15pt; background:#1db954; color:white; border-radius:12px; padding:12px 32px;')
        exportify_btn.clicked.connect(lambda: webbrowser.open('https://watsonbox.github.io/exportify/'))
        exportify_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        box1_layout.addWidget(exportify_btn, alignment=QtCore.Qt.AlignHCenter)
        box1.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        left_col.addWidget(box1)

        # Step 2: Input CSV and Download Directory
        box2 = QtWidgets.QGroupBox()
        box2.setStyleSheet(groupbox_style)
        box2_layout = QtWidgets.QVBoxLayout(box2)
        box2_layout.setSpacing(12)
        box2_layout.setContentsMargins(18, 12, 18, 12)
        step2 = QtWidgets.QLabel('Step 2: Load Your Exported CSV and Choose Download Directory')
        step2.setObjectName('sectionLabel')
        step2.setAlignment(QtCore.Qt.AlignHCenter)
        step2.setStyleSheet(label_style)
        box2_layout.addWidget(step2)

        # Input CSV row
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(10)
        input_label = QtWidgets.QLabel('Input CSV:')
        input_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setPlaceholderText('Pick the CSV file you exported from Exportify')
        self.input_edit.setToolTip('Pick the CSV file you exported from Exportify')
        self.input_edit.setStyleSheet('background: #18191a; color: #f5f5f7;')
        self.input_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.input_btn = QtWidgets.QPushButton('📂')
        self.input_btn.setToolTip('Browse for input CSV')
        self.input_btn.setFixedWidth(38)
        self.input_btn.clicked.connect(self.pick_input)
        input_row.addWidget(input_label)
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.input_btn)
        box2_layout.addLayout(input_row)

        # Download Directory row
        dir_row = QtWidgets.QHBoxLayout()
        dir_row.setSpacing(10)
        dir_label = QtWidgets.QLabel('Download Directory:')
        dir_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.download_dir_edit = QtWidgets.QLineEdit()
        self.download_dir_edit.setReadOnly(True)
        self.download_dir_edit.setPlaceholderText('Download directory')
        self.download_dir_edit.setStyleSheet('background: #18191a; color: #f5f5f7;')
        self.download_dir_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.download_dir_btn = QtWidgets.QPushButton('📁 Choose Download Directory')
        self.download_dir_btn.setToolTip('Pick a folder to save downloaded audio and CSVs')
        self.download_dir_btn.setFixedWidth(220)
        self.download_dir_btn.setStyleSheet('font-weight: bold; color: #1db954; background: #23272a; border: 2px solid #1db954; border-radius: 8px; font-size: 14pt;')
        self.download_dir_btn.clicked.connect(self.pick_download_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.download_dir_edit)
        dir_row.addWidget(self.download_dir_btn)
        box2_layout.addLayout(dir_row)

        # Thread count slider row
        thread_row = QtWidgets.QHBoxLayout()
        thread_row.setSpacing(10)
        thread_label = QtWidgets.QLabel('Threads:')
        thread_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.thread_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.thread_slider.setMinimum(1)
        self.thread_slider.setMaximum(os.cpu_count() or 4)
        self.thread_slider.setValue(1)
        self.thread_slider.setTickInterval(1)
        self.thread_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.thread_slider.setSingleStep(1)
        self.thread_slider.setFixedWidth(180)
        self.thread_slider.valueChanged.connect(self.update_thread_label)
        self.thread_value_label = QtWidgets.QLabel(str(self.thread_count))
        self.thread_value_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        thread_row.addWidget(thread_label)
        thread_row.addWidget(self.thread_slider)
        thread_row.addWidget(self.thread_value_label)
        box2_layout.addLayout(thread_row)

        # Audio format dropdown row
        format_row = QtWidgets.QHBoxLayout()
        format_row.setSpacing(10)
        format_label = QtWidgets.QLabel('Audio Format:')
        format_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(['opus', 'flac', 'mp3'])
        self.format_combo.setCurrentText('opus')
        self.format_combo.setFixedWidth(120)
        self.format_combo.currentTextChanged.connect(self.update_audio_format)
        format_row.addWidget(format_label)
        format_row.addWidget(self.format_combo)
        box2_layout.addLayout(format_row)

        box2.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        left_col.addWidget(box2)
        left_col.addStretch(1)

        # Right column: Step 3, Step 4, Progress, Log
        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(12)
        main_layout.addLayout(right_col, 1)

        # Step 3: Controls
        box4 = QtWidgets.QGroupBox()
        box4.setStyleSheet(groupbox_style)
        box4_layout = QtWidgets.QVBoxLayout(box4)
        box4_layout.setSpacing(8)
        box4_layout.setContentsMargins(18, 12, 18, 12)
        section3 = QtWidgets.QLabel('Step 3: Start')
        section3.setObjectName('sectionLabel')
        section3.setAlignment(QtCore.Qt.AlignHCenter)
        section3.setStyleSheet(label_style)
        box4_layout.addWidget(section3)
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton('Start')
        self.start_btn.setToolTip('Start fetching YouTube links and downloading audio')
        self.start_btn.setStyleSheet('font-size:15pt; background:#4CAF50; color:white; border-radius:10px; padding:10px 32px;')
        self.pause_btn = QtWidgets.QPushButton('Pause')
        self.resume_btn = QtWidgets.QPushButton('Resume')
        self.stop_btn = QtWidgets.QPushButton('Stop')
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.resume_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch(1)
        box4_layout.addLayout(btn_layout)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        box4.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        right_col.addWidget(box4)

        # Spinner/indicator
        self.spinner = QtWidgets.QLabel()
        self.spinner.setText('')
        self.spinner.setAlignment(QtCore.Qt.AlignHCenter)
        self.spinner.setStyleSheet('background: transparent;')
        right_col.addWidget(self.spinner)

        # Progress
        box5 = QtWidgets.QGroupBox()
        box5.setStyleSheet(groupbox_style)
        box5_layout = QtWidgets.QVBoxLayout(box5)
        box5_layout.setSpacing(8)
        box5_layout.setContentsMargins(18, 12, 18, 12)
        section4 = QtWidgets.QLabel('Progress')
        section4.setObjectName('sectionLabel')
        section4.setAlignment(QtCore.Qt.AlignHCenter)
        section4.setStyleSheet(label_style)
        box5_layout.addWidget(section4)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet('background: #18191a; color: #f5f5f7;')
        box5_layout.addWidget(self.progress)
        self.counters_lbl = QtWidgets.QLabel('Completed: 0 | Skipped: 0 | Failed: 0 | Total: 0')
        self.counters_lbl.setAlignment(QtCore.Qt.AlignHCenter)
        self.counters_lbl.setStyleSheet(label_style)
        box5_layout.addWidget(self.counters_lbl)
        box5.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        right_col.addWidget(box5)

        # Log
        box6 = QtWidgets.QGroupBox()
        box6.setStyleSheet(groupbox_style)
        box6_layout = QtWidgets.QVBoxLayout(box6)
        box6_layout.setSpacing(8)
        box6_layout.setContentsMargins(18, 12, 18, 12)
        section5 = QtWidgets.QLabel('Log')
        section5.setObjectName('sectionLabel')
        section5.setAlignment(QtCore.Qt.AlignHCenter)
        section5.setStyleSheet(label_style)
        box6_layout.addWidget(section5)
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        font = QtGui.QFont('Fira Mono', 10)
        self.log_area.setFont(font)
        self.log_area.setMinimumHeight(120)
        self.log_area.setStyleSheet('background: #18191a; color: #f5f5f7;')
        box6_layout.addWidget(self.log_area)
        box6.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        right_col.addWidget(box6)
        right_col.addStretch(1)

        # Connect buttons
        self.start_btn.clicked.connect(self.start_fetch)
        self.pause_btn.clicked.connect(self.pause)
        self.resume_btn.clicked.connect(self.resume)
        self.stop_btn.clicked.connect(self.stop)
        self.input_edit.textChanged.connect(self.auto_suggest_outputs)

    def auto_suggest_outputs(self):
        path = self.input_edit.text()
        if not path:
            self.download_dir_edit.setText("")
            return
        self.download_dir_edit.setText(os.path.dirname(path) or os.getcwd())

    def pick_input(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select Input CSV', '', 'CSV Files (*.csv)')
        if file:
            self.input_edit.setText(file)
    def pick_download_dir(self):
        dir_ = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Download Directory', os.getcwd())
        if dir_:
            self.download_dir_edit.setText(dir_)

    def update_thread_label(self, value):
        self.thread_count = value
        self.thread_value_label.setText(str(value))

    def update_audio_format(self, value):
        self.audio_format = value

    def start_fetch(self):
        input_csv = self.input_edit.text().strip()
        download_dir = self.download_dir_edit.text().strip() or os.getcwd()
        if not input_csv:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Input CSV field must not be empty!')
            return
        if not os.path.exists(input_csv):
            QtWidgets.QMessageBox.critical(self, 'Error', 'Input CSV does not exist!')
            return
        base = os.path.splitext(os.path.basename(input_csv))[0]
        output_csv = os.path.join(download_dir, base + '_links.csv')
        failed_csv = os.path.join(download_dir, base + '_failed.csv')
        self.log_area.clear()
        self.completed = self.skipped = self.failed = self.total = 0
        self.progress.setValue(0)
        self.pause_event.clear()
        self.stop_event.clear()
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        from spotube_app import Worker  # Avoid circular import
        self.worker = Worker(input_csv, output_csv, failed_csv, self.pause_event, self.stop_event, True, download_dir, self.thread_count, self.audio_format)
        self.worker.progress_signal.connect(self.handle_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def pause(self):
        self.pause_event.set()
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(True)
    def resume(self):
        self.pause_event.clear()
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
    def stop(self):
        self.stop_event.set()
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
    def handle_progress(self, msg):
        # Suppress repeated download errors, only show a summary at the end
        if not hasattr(self, '_error_urls'):
            self._error_urls = set()
            self._error_count = 0
        if msg['type'] == 'log':
            if 'Failed to download' in msg['msg']:
                url = msg['msg'].split('Failed to download ')[-1].split(':')[0].strip()
                if url not in self._error_urls:
                    self._error_urls.add(url)
                    self._error_count += 1
            elif 'error' in msg['msg'].lower():
                self.log_area.appendHtml(f'<span style="color:#ff5555;">{msg["msg"]}</span>')
            else:
                self.log_area.appendPlainText(msg['msg'])
            self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
        elif msg['type'] == 'progress':
            self.completed = msg.get('completed', self.completed)
            self.skipped = msg.get('skipped', self.skipped)
            self.failed = msg.get('failed', self.failed)
            self.total = msg.get('total', self.total)
            prog = int(100 * (self.completed + self.skipped + self.failed) / self.total) if self.total else 0
            self.progress.setValue(prog)
            self.counters_lbl.setText(f'Completed: {self.completed} | Skipped: {self.skipped} | Failed: {self.failed} | Total: {self.total}')
        elif msg['type'] == 'error':
            self.log_area.appendHtml(f'<span style="color:#ff5555;">{msg["msg"]}</span>')
            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()

    def on_finished(self):
        # Show summary of download errors if any
        if hasattr(self, '_error_count') and self._error_count > 0:
            self.log_area.appendHtml(f'<span style="color:#ff5555;">{self._error_count} downloads failed. See failed CSV for details.</span>')
        self.spinner.setText('')
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.log_area.appendHtml('<b style="color:#4CAF50;">All done!</b>')
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('logo.png'))
    window = SpotubeApp()
    window.show()
    sys.exit(app.exec_()) 