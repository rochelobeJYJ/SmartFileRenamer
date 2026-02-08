# -*- coding: utf-8 -*-
"""
Smart File Renamer (스마트 파일 리네이머)
HWP/PDF 파일 분석 및 자동 이름 변경 도구
Version: 1.0.0
"""

import sys
import json
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QGroupBox, QMessageBox, QFileDialog, QHeaderView,
    QAbstractItemView, QStatusBar, QProgressBar, QFrame, QTextEdit,
    QComboBox, QDialog, QDialogButtonBox, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QAction, QFont

from processor import FileProcessor, FileEntry
from config import FileStatus, STATUS_COLORS, DEFAULT_RENAME_PATTERN

CONFIG_FILE = Path(__file__).parent / "user_config.json"


class AnalyzeThread(QThread):
    """파일 분석 스레드"""
    progress = Signal(int, int)
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, processor: FileProcessor, entries: List[FileEntry]):
        super().__init__()
        self.processor = processor
        self.entries = entries
        
    def run(self):
        try:
            total = len(self.entries)
            for i, entry in enumerate(self.entries):
                self.processor.analyze_file(entry)
                self.progress.emit(i + 1, total)
            self.finished.emit(self.entries)
        except Exception as e:
            self.error.emit(str(e))


class EditInfoDialog(QDialog):
    """추출 정보 편집 다이얼로그"""
    
    def __init__(self, entry: FileEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle("추출 정보 수정")
        self.setMinimumWidth(350)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        file_label = QLabel(f"파일: {self.entry.original_name}{self.entry.extension}")
        file_label.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(file_label)
        layout.addSpacing(8)
        
        form_layout = QFormLayout()
        self.year_input = QLineEdit(self.entry.extracted_info.year)
        self.year_input.setPlaceholderText("예: 2024")
        form_layout.addRow("연도:", self.year_input)
        
        self.month_input = QLineEdit(self.entry.extracted_info.month)
        self.month_input.setPlaceholderText("예: 03")
        form_layout.addRow("월:", self.month_input)
        
        self.grade_input = QLineEdit(self.entry.extracted_info.grade)
        self.grade_input.setPlaceholderText("예: 고3, 중2")
        self.grade_input.setToolTip("학년 (고1, 고2, 고3 등)")
        form_layout.addRow("학년:", self.grade_input)
        
        self.subject_input = QLineEdit(self.entry.extracted_info.subject)
        self.subject_input.setPlaceholderText("예: 물리, 화학, 국어 등")
        form_layout.addRow("분류:", self.subject_input)
        layout.addLayout(form_layout)
        
        if self.entry.extracted_info.header_text:
            layout.addSpacing(8)
            layout.addWidget(QLabel("📄 문서 상단 텍스트 (참고):"))
            header_text = QTextEdit()
            header_text.setPlainText(self.entry.extracted_info.header_text[:300])
            header_text.setReadOnly(True)
            header_text.setMaximumHeight(80)
            header_text.setStyleSheet("font-size: 10px; background-color: #f5f5f5;")
            layout.addWidget(header_text)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_values(self) -> dict:
        return {
            'year': self.year_input.text().strip(),
            'month': self.month_input.text().strip(),
            'grade': self.grade_input.text().strip(),
            'subject': self.subject_input.text().strip()
        }


class DropArea(QFrame):
    """드래그 앤 드롭 영역"""
    filesDropped = Signal(list)
    
    STYLE_NORMAL = "DropArea { border: 2px dashed #aaa; border-radius: 6px; background-color: #f8f8f8; }"
    STYLE_HOVER = "DropArea { border: 2px dashed #0078d4; border-radius: 6px; background-color: #e8f4fc; }"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.setMinimumHeight(50)
        self.setMaximumHeight(60)
        self.setStyleSheet(self.STYLE_NORMAL)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        label = QLabel("📁 드래그 앤 드롭")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(label)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.STYLE_HOVER)
            
    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.STYLE_NORMAL)
        
    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self.STYLE_NORMAL)
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
            if paths:
                self.filesDropped.emit(paths)


class PatternBlock(QFrame):
    """패턴 블록"""
    removed = Signal(object)
    
    def __init__(self, name: str, display: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.display = display
        
        self.setStyleSheet("""
            PatternBlock { background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 4px; }
            PatternBlock:hover { background-color: #bbdefb; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(2)
        
        self.label = QLabel(display)
        self.label.setStyleSheet("font-size: 10px; color: #1565c0;")
        layout.addWidget(self.label)
        
        btn_remove = QPushButton("×")
        btn_remove.setFixedSize(14, 14)
        btn_remove.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #666; font-weight: bold; font-size: 11px; }
            QPushButton:hover { color: #d32f2f; }
        """)
        btn_remove.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(btn_remove)


class PatternEditor(QWidget):
    """패턴 에디터"""
    patternChanged = Signal(str)
    
    AVAILABLE_BLOCKS = [
        ("{Year}", "연도"),
        ("{Month}", "월"),
        ("{Subject}", "분류"),
        ("{Original}", "원본명"),
        ("{Seq}", "연번"),
        ("{Grade}", "학년"),  # 학년 (고1, 고2, 고3 등)
    ]
    CUSTOM_BLOCK_NAME = "{Custom}"
    SEPARATORS = ["_", "-", ".", " ", ""]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.blocks = []
        self.separator = "_"
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 블록 추가
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("블록:"))
        
        btn_style = """
            QPushButton { background-color: #f5f5f5; border: 1px solid #ddd;
                border-radius: 3px; padding: 2px 6px; font-size: 10px; }
            QPushButton:hover { background-color: #e3f2fd; border-color: #90caf9; }
        """
        for name, display in self.AVAILABLE_BLOCKS:
            btn = QPushButton(f"+{display}")
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, n=name, d=display: self.add_block(n, d))
            add_layout.addWidget(btn)
        
        # 직접 입력 블록
        add_layout.addWidget(QLabel(" | "))
        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("직접 입력")
        self.custom_input.setFixedWidth(70)
        self.custom_input.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        add_layout.addWidget(self.custom_input)
        
        btn_add_custom = QPushButton("+추가")
        btn_add_custom.setStyleSheet(btn_style)
        btn_add_custom.clicked.connect(self._add_custom_block)
        add_layout.addWidget(btn_add_custom)
        
        add_layout.addStretch()
        layout.addLayout(add_layout)
        
        # 블록 표시
        block_container = QFrame()
        block_container.setStyleSheet("QFrame { background-color: #fafafa; border: 1px solid #ddd; border-radius: 4px; }")
        self.block_layout = QHBoxLayout(block_container)
        self.block_layout.setContentsMargins(4, 4, 4, 4)
        self.block_layout.setSpacing(3)
        
        self.lbl_empty = QLabel("← 블록 추가 또는 아래 직접 입력")
        self.lbl_empty.setStyleSheet("color: #999; font-size: 10px;")
        self.block_layout.addWidget(self.lbl_empty)
        self.block_layout.addStretch()
        layout.addWidget(block_container)
        
        # 구분자 + 순서
        sep_layout = QHBoxLayout()
        sep_layout.addWidget(QLabel("구분자:"))
        self.sep_combo = QComboBox()
        self.sep_combo.addItems(["_ (밑줄)", "- (하이픈)", ". (점)", "  (공백)", "(없음)"])
        self.sep_combo.setFixedWidth(90)
        self.sep_combo.currentIndexChanged.connect(self._on_separator_changed)
        sep_layout.addWidget(self.sep_combo)
        
        # ◀ 왼쪽으로 이동 (첫 번째를 마지막으로)
        self.btn_move_left = QPushButton("◀")
        self.btn_move_left.setFixedWidth(28)
        self.btn_move_left.setToolTip("블록 순서 회전 (왼쪽)")
        self.btn_move_left.clicked.connect(self._rotate_blocks_left)
        sep_layout.addWidget(self.btn_move_left)
        
        # ▶ 오른쪽으로 이동 (마지막을 첫 번째로)
        self.btn_move_right = QPushButton("▶")
        self.btn_move_right.setFixedWidth(28)
        self.btn_move_right.setToolTip("블록 순서 회전 (오른쪽)")
        self.btn_move_right.clicked.connect(self._rotate_blocks_right)
        sep_layout.addWidget(self.btn_move_right)
        
        self.btn_clear_blocks = QPushButton("지우기")
        self.btn_clear_blocks.clicked.connect(self.clear_blocks)
        sep_layout.addWidget(self.btn_clear_blocks)
        sep_layout.addStretch()
        layout.addLayout(sep_layout)
        
        # 직접 입력
        direct_layout = QHBoxLayout()
        direct_layout.addWidget(QLabel("패턴:"))
        self.pattern_input = QLineEdit(DEFAULT_RENAME_PATTERN)
        self.pattern_input.textChanged.connect(lambda t: self.patternChanged.emit(t))
        direct_layout.addWidget(self.pattern_input)
        layout.addLayout(direct_layout)
        
        self.set_pattern(DEFAULT_RENAME_PATTERN)
        
    def _add_custom_block(self):
        """직접 입력 블록 추가"""
        text = self.custom_input.text().strip()
        if text:
            self.add_block(text, text)  # 직접 입력은 이름과 표시가 동일
            self.custom_input.clear()
        
    def add_block(self, name: str, display: str):
        block = PatternBlock(name, display)
        block.removed.connect(self.remove_block)
        self.blocks.append(block)
        self.lbl_empty.hide()
        
        self.block_layout.takeAt(self.block_layout.count() - 1)
        self.block_layout.addWidget(block)
        self.block_layout.addStretch()
        self._update_pattern()
        
    def remove_block(self, block: PatternBlock):
        if block in self.blocks:
            self.blocks.remove(block)
            block.deleteLater()
        if not self.blocks:
            self.lbl_empty.show()
        self._update_pattern()
        
    def clear_blocks(self):
        for block in self.blocks[:]:
            block.deleteLater()
        self.blocks.clear()
        self.lbl_empty.show()
        self._update_pattern()
        
    def _rotate_blocks_left(self):
        """◀ 버튼: 블록을 왼쪽으로 회전 (첫 번째 → 마지막)"""
        if len(self.blocks) >= 2:
            self.blocks.append(self.blocks.pop(0))
            self._refresh_block_display()
            self._update_pattern()
            
    def _rotate_blocks_right(self):
        """▶ 버튼: 블록을 오른쪽으로 회전 (마지막 → 첫 번째)"""
        if len(self.blocks) >= 2:
            self.blocks.insert(0, self.blocks.pop())
            self._refresh_block_display()
            self._update_pattern()
            
    def _refresh_block_display(self):
        while self.block_layout.count():
            item = self.block_layout.takeAt(0)
            if item.widget() and item.widget() != self.lbl_empty:
                item.widget().setParent(None)
        
        if self.blocks:
            self.lbl_empty.hide()
            for block in self.blocks:
                self.block_layout.addWidget(block)
        else:
            self.block_layout.addWidget(self.lbl_empty)
            self.lbl_empty.show()
        self.block_layout.addStretch()
        
    def _on_separator_changed(self, index: int):
        self.separator = self.SEPARATORS[index]
        self._update_pattern()
        
    def _update_pattern(self):
        if self.blocks:
            pattern = self.separator.join([b.name for b in self.blocks])
            self.pattern_input.blockSignals(True)
            self.pattern_input.setText(pattern)
            self.pattern_input.blockSignals(False)
            self.patternChanged.emit(pattern)
            
    def set_pattern(self, pattern: str):
        self.clear_blocks()
        self.pattern_input.setText(pattern)
        for name, display in self.AVAILABLE_BLOCKS:
            if name in pattern:
                self.add_block(name, display)
                
    def get_pattern(self) -> str:
        return self.pattern_input.text()


class SmartFileRenamer(QMainWindow):
    """메인 윈도우"""
    
    # 기본 분류 키워드 (UI 추천용)
    DEFAULT_KEYWORDS = [
        # === 주요 과목 ===
        "국어", "수학", "영어", "한국사",
        "과학", "사회", "탐구", "역사", "도덕", "기가",
        
        # === 세분류 ===
        "물리", "화학", "생명과학", "지구과학",
        "통합과학", "통합사회",
        "미적분", "기하", "확통",
        "화작", "언매", "독서", "문학",
        "영어회화", "영작문",
        "일본어", "중국어",
        
        # === 학교생활기록부 (생기부) ===
        "생기부", "세무능력", "세특", "과세특", # 세무능력 -> 세부능력 오타일 수 있으니 사용자가 흔히 쓰는 말로
        "창의적체험", "창체", "자동봉진",
        "자율활동", "동아리", "봉사활동", "진로활동",
        "행동특성", "행특", "행발",
        "독서활동", "수상경력",
        
        # === 문서 유형 ===
        "보고서", "계획서", "신청서", "평가서",
        "회의록", "상담록",
        "시험지", "문제지", "해설지", "정답지",
        "수행평가", "중간고사", "기말고사",
    ]
    
    def __init__(self):
        super().__init__()
        self.processor = FileProcessor()
        self.entries: List[FileEntry] = []
        self.analyze_thread: Optional[AnalyzeThread] = None
        self.user_keywords: List[str] = []
        self.dest_folder: Optional[str] = None
        
        self._load_user_config()
        self._init_ui()
        
    def _init_ui(self):
        self.setWindowTitle("스마트 파일 리네이머")
        self.setMinimumSize(930, 550)
        self.resize(1030, 610)  # 가로 3% 증가 (1000 -> 1030)
        
        self._create_menu_bar()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)
        
        self._create_settings_area(main_layout)
        
        content_layout = QHBoxLayout()
        content_layout.addWidget(self._create_file_selection_panel())
        content_layout.addWidget(self._create_file_list_panel(), 3)
        main_layout.addLayout(content_layout, 1)
        
        self._create_action_buttons(main_layout)
        
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.hide()
        self.statusBar.addPermanentWidget(self.progress_bar)
        self._update_status("준비됨")
        
    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("파일(&F)")
        
        open_folder = QAction("폴더 열기(&O)", self)
        open_folder.setShortcut("Ctrl+O")
        open_folder.triggered.connect(self._select_folder)
        file_menu.addAction(open_folder)
        
        open_files = QAction("파일 선택(&S)", self)
        open_files.setShortcut("Ctrl+Shift+O")
        open_files.triggered.connect(self._select_files)
        file_menu.addAction(open_files)
        
        file_menu.addSeparator()
        
        exit_action = QAction("종료(&X)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menubar.addMenu("편집(&E)")
        
        undo_action = QAction("되돌리기(&U)", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo_last_rename)
        edit_menu.addAction(undo_action)
        
        edit_menu.addSeparator()
        
        clear_action = QAction("목록 비우기(&C)", self)
        clear_action.triggered.connect(self._clear_list)
        edit_menu.addAction(clear_action)
        
        help_menu = menubar.addMenu("도움말(&H)")
        
        about_action = QAction("정보(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
    def _create_settings_area(self, parent_layout):
        settings_layout = QHBoxLayout()
        
        # 패턴 설정
        pattern_group = QGroupBox("📝 파일명 패턴")
        pattern_layout = QVBoxLayout(pattern_group)
        pattern_layout.setContentsMargins(6, 10, 6, 6)
        pattern_layout.setSpacing(4)
        
        self.pattern_editor = PatternEditor()
        self.pattern_editor.patternChanged.connect(self._on_pattern_changed)
        pattern_layout.addWidget(self.pattern_editor)
        settings_layout.addWidget(pattern_group, 2)
        
        # 키워드
        keyword_group = QGroupBox("🏷️ 분류 키워드")
        keyword_layout = QVBoxLayout(keyword_group)
        keyword_layout.setContentsMargins(6, 10, 6, 6)
        keyword_layout.setSpacing(4)
        
        self.keyword_text = QTextEdit()
        self.keyword_text.setPlaceholderText("한 줄에 하나씩...")
        keywords_to_show = self.user_keywords if self.user_keywords else self.DEFAULT_KEYWORDS
        self.keyword_text.setText("\n".join(keywords_to_show))
        self.keyword_text.setMaximumHeight(70)
        keyword_layout.addWidget(self.keyword_text)
        
        keyword_btn_layout = QHBoxLayout()
        
        btn_save = QPushButton("💾 저장")
        btn_save.clicked.connect(self._save_keywords)
        btn_save.setStyleSheet("""
            QPushButton { background-color: #4caf50; color: white; border: none; border-radius: 3px; padding: 3px 8px; }
            QPushButton:hover { background-color: #43a047; }
        """)
        keyword_btn_layout.addWidget(btn_save)
        
        btn_reset = QPushButton("↺ 기본값")
        btn_reset.clicked.connect(self._reset_keywords)
        keyword_btn_layout.addWidget(btn_reset)
        keyword_btn_layout.addStretch()
        keyword_layout.addLayout(keyword_btn_layout)
        
        settings_layout.addWidget(keyword_group, 1)
        parent_layout.addLayout(settings_layout)
        
    def _create_file_selection_panel(self) -> QWidget:
        widget = QWidget()
        widget.setFixedWidth(220)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)
        
        # 파일 선택
        group = QGroupBox("📂 파일 선택")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(6, 10, 6, 6)
        group_layout.setSpacing(4)
        
        self.drop_area = DropArea()
        self.drop_area.filesDropped.connect(self._handle_dropped_files)
        group_layout.addWidget(self.drop_area)
        
        btn_layout = QHBoxLayout()
        self.btn_select_folder = QPushButton("📁 폴더")
        self.btn_select_folder.clicked.connect(self._select_folder)
        self.btn_select_folder.setMinimumHeight(28)
        btn_layout.addWidget(self.btn_select_folder)
        
        self.btn_select_files = QPushButton("📄 파일")
        self.btn_select_files.clicked.connect(self._select_files)
        self.btn_select_files.setMinimumHeight(28)
        btn_layout.addWidget(self.btn_select_files)
        group_layout.addLayout(btn_layout)
        
        self.lbl_file_count = QLabel("선택: 0개")
        self.lbl_file_count.setStyleSheet("color: #666; font-size: 10px;")
        group_layout.addWidget(self.lbl_file_count)
        layout.addWidget(group)
        
        # 저장 위치
        dest_group = QGroupBox("📁 저장 위치")
        dest_layout = QVBoxLayout(dest_group)
        dest_layout.setContentsMargins(6, 10, 6, 6)
        dest_layout.setSpacing(4)
        
        self.dest_label = QLabel("원본 위치에서 이름만 변경")
        self.dest_label.setWordWrap(True)
        self.dest_label.setStyleSheet("color: #666; font-size: 9px;")
        dest_layout.addWidget(self.dest_label)
        
        dest_btn_layout = QHBoxLayout()
        btn_set = QPushButton("지정")
        btn_set.clicked.connect(self._set_destination_folder)
        dest_btn_layout.addWidget(btn_set)
        
        self.btn_clear_dest = QPushButton("해제")
        self.btn_clear_dest.clicked.connect(self._clear_destination_folder)
        self.btn_clear_dest.setEnabled(False)
        dest_btn_layout.addWidget(self.btn_clear_dest)
        dest_layout.addLayout(dest_btn_layout)
        layout.addWidget(dest_group)
        
        # 상세 정보
        detail_group = QGroupBox("📄 상세 정보")
        detail_layout = QVBoxLayout(detail_group)
        detail_layout.setContentsMargins(6, 10, 6, 6)
        
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("파일 선택 시 표시")
        self.detail_text.setMaximumHeight(100)
        self.detail_text.setStyleSheet("font-size: 9px;")
        detail_layout.addWidget(self.detail_text)
        layout.addWidget(detail_group)
        
        layout.addStretch()
        return widget
        
    def _create_file_list_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(4)
        
        # 헤더
        header_layout = QHBoxLayout()
        
        header_label = QLabel("📋 파일 목록")
        header_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        header_layout.addWidget(header_label)
        
        hint_label = QLabel("💡 분류 인식이 틀릴 수 있습니다. 추출정보 열을 더블클릭하여 수정하세요.")
        hint_label.setStyleSheet("color: #888; font-size: 9px;")
        header_layout.addWidget(hint_label)
        
        header_layout.addStretch()
        
        # 순서 변경
        self.btn_move_up = QPushButton("▲")
        self.btn_move_up.clicked.connect(self._move_item_up)
        self.btn_move_up.setFixedWidth(28)
        self.btn_move_up.setToolTip("위로")
        header_layout.addWidget(self.btn_move_up)
        
        self.btn_move_down = QPushButton("▼")
        self.btn_move_down.clicked.connect(self._move_item_down)
        self.btn_move_down.setFixedWidth(28)
        self.btn_move_down.setToolTip("아래로")
        header_layout.addWidget(self.btn_move_down)
        
        # 필터
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["전체", "확인필요", "준비됨"])
        self.filter_combo.setFixedWidth(75)
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        header_layout.addWidget(self.filter_combo)
        
        # 버튼 스타일 통일
        btn_style = "QPushButton { padding: 3px 8px; }"
        
        btn_edit = QPushButton("✏️ 수정")
        btn_edit.clicked.connect(self._edit_selected_info)
        btn_edit.setToolTip("선택한 파일의 추출 정보 수정")
        btn_edit.setStyleSheet(btn_style)
        header_layout.addWidget(btn_edit)
        
        btn_delete = QPushButton("🗑️ 선택 삭제")
        btn_delete.clicked.connect(self._delete_selected_files)
        btn_delete.setToolTip("선택된 파일을 목록에서 제거")
        btn_delete.setStyleSheet(btn_style)
        header_layout.addWidget(btn_delete)
        
        btn_preview = QPushButton("🔍 미리보기")
        btn_preview.clicked.connect(self._apply_preview)
        btn_preview.setStyleSheet(btn_style)
        header_layout.addWidget(btn_preview)
        
        layout.addLayout(header_layout)
        
        # 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "원본", "추출정보", "새이름", "상태"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 35)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 60)
        
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._show_file_details)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        # Delete 키 처리
        self.table.keyPressEvent = self._table_key_press
        
        layout.addWidget(self.table)
        return widget
        
    def _table_key_press(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_files()
        else:
            QTableWidget.keyPressEvent(self.table, event)
        
    def _create_action_buttons(self, parent_layout):
        btn_layout = QHBoxLayout()
        
        btn_undo = QPushButton("↩️ 되돌리기")
        btn_undo.clicked.connect(self._undo_last_rename)
        btn_undo.setMinimumHeight(32)
        btn_undo.setStyleSheet("""
            QPushButton { background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; padding: 5px 10px; }
            QPushButton:hover { background-color: #e0e0e0; }
        """)
        btn_layout.addWidget(btn_undo)
        
        btn_layout.addStretch()
        
        btn_clear = QPushButton("🗑️ 전체 비우기")
        btn_clear.clicked.connect(self._clear_list)
        btn_clear.setMinimumHeight(32)
        btn_layout.addWidget(btn_clear)
        
        self.btn_execute = QPushButton("✅ 실행")
        self.btn_execute.clicked.connect(self._execute_rename)
        self.btn_execute.setMinimumHeight(32)
        self.btn_execute.setStyleSheet("""
            QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 4px; padding: 5px 18px; font-weight: bold; }
            QPushButton:hover { background-color: #106ebe; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        btn_layout.addWidget(self.btn_execute)
        
        parent_layout.addLayout(btn_layout)
        
    # === 유틸리티 메서드 ===
    
    def _update_status(self, message: str):
        self.statusBar.showMessage(message)
        
    def _load_user_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.user_keywords = config.get('keywords', [])
        except Exception:
            self.user_keywords = []
            
    def _save_user_config(self):
        try:
            config = {'keywords': self.user_keywords}
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"저장 실패: {e}")
            
    def _save_keywords(self):
        keywords_text = self.keyword_text.toPlainText()
        self.user_keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
        self._save_user_config()
        self.processor.set_custom_keywords(self.user_keywords)
        QMessageBox.information(self, "저장", f"{len(self.user_keywords)}개 키워드 저장됨")
        
    def _reset_keywords(self):
        self.keyword_text.setText("\n".join(self.DEFAULT_KEYWORDS))
        
    def _set_destination_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "저장 폴더")
        if folder:
            self.dest_folder = folder
            short_path = folder if len(folder) < 30 else "..." + folder[-27:]
            self.dest_label.setText(f"📁 {short_path}")
            self.dest_label.setStyleSheet("color: #1565c0; font-size: 9px;")
            self.btn_clear_dest.setEnabled(True)
            
    def _clear_destination_folder(self):
        self.dest_folder = None
        self.dest_label.setText("원본 위치에서 이름만 변경")
        self.dest_label.setStyleSheet("color: #666; font-size: 9px;")
        self.btn_clear_dest.setEnabled(False)
        
    def _on_pattern_changed(self, pattern: str):
        if self.entries:
            self._apply_preview()
        
    # === 파일 선택 ===
    
    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder:
            self._load_files([folder])
            
    def _select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "파일 선택", "", "지원 파일 (*.hwp *.hwpx *.pdf)"
        )
        if files:
            self._load_files(files)
            
    def _handle_dropped_files(self, paths: List[str]):
        self._load_files(paths)
        
    def _load_files(self, paths: List[str]):
        new_entries = self.processor.scan_files(paths)
        if not new_entries:
            QMessageBox.information(self, "알림", "지원되는 파일이 없습니다.")
            return
        
        self.entries.extend(new_entries)
        self.lbl_file_count.setText(f"선택: {len(self.entries)}개")
        self._start_analysis(new_entries)
        
    # === 분석 ===
    
    def _start_analysis(self, entries: List[FileEntry]):
        self.progress_bar.show()
        self.progress_bar.setRange(0, len(entries))
        self.progress_bar.setValue(0)
        self._update_status("분석 중...")
        
        self.btn_execute.setEnabled(False)
        self.btn_select_folder.setEnabled(False)
        self.btn_select_files.setEnabled(False)
        
        keywords_text = self.keyword_text.toPlainText()
        keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
        self.processor.set_custom_keywords(keywords)
        
        self.analyze_thread = AnalyzeThread(self.processor, entries)
        self.analyze_thread.progress.connect(self._on_analysis_progress)
        self.analyze_thread.finished.connect(self._on_analysis_finished)
        self.analyze_thread.error.connect(self._on_analysis_error)
        self.analyze_thread.start()
        
    def _on_analysis_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)
        self._update_status(f"분석 중... ({current}/{total})")
        
    def _on_analysis_finished(self, entries: List[FileEntry]):
        self.progress_bar.hide()
        self._update_status(f"분석 완료: {len(entries)}개")
        
        self.btn_execute.setEnabled(True)
        self.btn_select_folder.setEnabled(True)
        self.btn_select_files.setEnabled(True)
        
        self._apply_preview()
        
    def _on_analysis_error(self, error: str):
        self.progress_bar.hide()
        self._update_status("오류 발생")
        
        self.btn_execute.setEnabled(True)
        self.btn_select_folder.setEnabled(True)
        self.btn_select_files.setEnabled(True)
        
        QMessageBox.warning(self, "오류", f"분석 중 오류:\n{error}")
        
    # === 미리보기 및 테이블 ===
    
    def _apply_preview(self):
        if not self.entries:
            self._update_status("미리보기할 파일이 없습니다.")
            return
            
        pattern = self.pattern_editor.get_pattern() or DEFAULT_RENAME_PATTERN
        
        keywords_text = self.keyword_text.toPlainText()
        keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
        self.processor.set_custom_keywords(keywords)
        
        self.entries = self.processor.generate_all_names(self.entries, pattern)
        self.entries = self.processor.check_duplicates(self.entries, self.dest_folder)
        self._update_table()
        self._update_status(f"미리보기 적용됨 (패턴: {pattern[:30]}...)" if len(pattern) > 30 else f"미리보기 적용됨 (패턴: {pattern})")
        
    def _update_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.entries))
        
        seq_format = "{:03d}" if len(self.entries) >= 100 else "{:02d}"
        
        for row, entry in enumerate(self.entries):
            # 순번
            item0 = QTableWidgetItem(seq_format.format(row + 1))
            item0.setFlags(item0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item0.setData(Qt.ItemDataRole.UserRole, entry)
            item0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item0)
            
            # 원본
            item1 = QTableWidgetItem(entry.original_name + entry.extension)
            item1.setFlags(item1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item1)
            
            # 추출정보
            info = entry.extracted_info
            info_parts = []
            if info.year:
                info_parts.append(info.year)
            if info.month:
                info_parts.append(f"{info.month}월")
            if info.grade:
                info_parts.append(info.grade)
            if info.subject:
                subject_display = ""
                if info.subject_sub and info.subject_main and info.subject_sub != info.subject_main:
                    subject_display = f"{info.subject_main}>{info.subject_sub}"
                else:
                    subject_display = info.subject
                # 스마트 추출된 경우 표시
                if info.is_smart_extracted:
                    subject_display = f"✨{subject_display}"
                info_parts.append(subject_display)
            
            item2 = QTableWidgetItem(" | ".join(info_parts) if info_parts else "(없음)")
            item2.setFlags(item2.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tooltip = "더블클릭하여 수정"
            if info.is_smart_extracted:
                tooltip += " (✨ 자동 감지됨)"
            item2.setToolTip(tooltip)
            self.table.setItem(row, 2, item2)
            
            # 새이름 (편집 가능)
            item3 = QTableWidgetItem(entry.proposed_name)
            self.table.setItem(row, 3, item3)
            
            # 상태
            item4 = QTableWidgetItem(entry.status)
            item4.setFlags(item4.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, item4)
            
            # 색상
            if entry.status in STATUS_COLORS:
                color = QColor(*STATUS_COLORS[entry.status])
                for col in range(5):
                    self.table.item(row, col).setBackground(color)
        
        self.table.blockSignals(False)
        
        needs_check = sum(1 for e in self.entries if e.status == FileStatus.NEEDS_CHECK)
        ready = sum(1 for e in self.entries if e.status == FileStatus.READY)
        dest_info = f" → {Path(self.dest_folder).name}" if self.dest_folder else ""
        self._update_status(f"총 {len(self.entries)}개 | 준비: {ready} | 확인필요: {needs_check}{dest_info}")
        
    def _on_cell_changed(self, row: int, column: int):
        if column == 3:
            item = self.table.item(row, 0)
            if item:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    entry.proposed_name = self.table.item(row, 3).text()
                    
    def _on_cell_double_clicked(self, row: int, column: int):
        if column == 2:
            item = self.table.item(row, 0)
            if item:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    self._show_edit_dialog(entry)
                    
    def _edit_selected_info(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "알림", "편집할 파일을 선택하세요.")
            return
            
        row = selected[0].row()
        item = self.table.item(row, 0)
        if item:
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry:
                self._show_edit_dialog(entry)
                
    def _show_edit_dialog(self, entry: FileEntry):
        dialog = EditInfoDialog(entry, self)
        if dialog.exec():
            values = dialog.get_values()
            entry.extracted_info.year = values['year']
            entry.extracted_info.month = values['month']
            entry.extracted_info.grade = values['grade']
            entry.extracted_info.subject = values['subject']
            
            if values['year'] or values['month'] or values['subject']:
                entry.status = FileStatus.READY
                
            self._apply_preview()
                    
    def _move_item_up(self):
        selected_rows = sorted(set(item.row() for item in self.table.selectedItems()))
        if not selected_rows or selected_rows[0] == 0:
            return
        
        for row in selected_rows:
            if row > 0:
                self.entries[row], self.entries[row - 1] = self.entries[row - 1], self.entries[row]
        
        self._apply_preview()
        self.table.clearSelection()
        for row in selected_rows:
            if row > 0:
                self.table.selectRow(row - 1)
                    
    def _move_item_down(self):
        selected_rows = sorted(set(item.row() for item in self.table.selectedItems()), reverse=True)
        if not selected_rows or selected_rows[0] == len(self.entries) - 1:
            return
        
        for row in selected_rows:
            if row < len(self.entries) - 1:
                self.entries[row], self.entries[row + 1] = self.entries[row + 1], self.entries[row]
        
        self._apply_preview()
        self.table.clearSelection()
        for row in selected_rows:
            if row < len(self.entries) - 1:
                self.table.selectRow(row + 1)
                    
    def _delete_selected_files(self):
        selected_rows = set(item.row() for item in self.table.selectedItems())
        if not selected_rows:
            return
            
        entries_to_remove = []
        for row in selected_rows:
            item = self.table.item(row, 0)
            if item:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    entries_to_remove.append(entry)
        
        for entry in entries_to_remove:
            if entry in self.entries:
                self.entries.remove(entry)
        
        self.lbl_file_count.setText(f"선택: {len(self.entries)}개")
        self._apply_preview()
                    
    def _apply_filter(self):
        filter_text = self.filter_combo.currentText()
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    show = True
                    if filter_text == "확인필요":
                        show = entry.status == FileStatus.NEEDS_CHECK
                    elif filter_text == "준비됨":
                        show = entry.status == FileStatus.READY
                    self.table.setRowHidden(row, not show)
                    
    def _show_file_details(self):
        selected = self.table.selectedItems()
        if not selected:
            self.detail_text.clear()
            return
            
        row = selected[0].row()
        item = self.table.item(row, 0)
        if item:
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry:
                info = entry.extracted_info
                subject_info = ""
                if info.subject_main and info.subject_sub:
                    subject_info = f"{info.subject_main}>{info.subject_sub}"
                elif info.subject:
                    subject_info = info.subject
                    
                details = f"""원본: {entry.original_name}
새이름: {entry.proposed_name}
━━ 추출 ━━
연:{info.year or '-'} 월:{info.month or '-'}
분류: {subject_info or '-'}"""
                self.detail_text.setText(details)
                
    # === 실행 ===
    
    def _execute_rename(self):
        if not self.entries:
            QMessageBox.information(self, "알림", "변경할 파일이 없습니다.")
            return
        
        action = "복사" if self.dest_folder else "이름 변경"
        dest = f"\n→ {self.dest_folder}" if self.dest_folder else ""
        
        reply = QMessageBox.question(
            self, "확인", f"{len(self.entries)}개 파일 {action}?{dest}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        success, fail, errors = self.processor.execute_rename(self.entries, self.dest_folder)
        self._update_table()
        
        if fail > 0:
            QMessageBox.warning(self, "결과", f"완료: {success}개\n실패: {fail}개")
        else:
            QMessageBox.information(self, "완료", f"{success}개 파일 {action} 완료!")
            
    def _undo_last_rename(self):
        reply = QMessageBox.question(
            self, "확인", "마지막 작업을 되돌리시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        success, msg = self.processor.undo_last_rename()
        
        if success:
            QMessageBox.information(self, "완료", msg)
            self._clear_list()
        else:
            QMessageBox.warning(self, "실패", msg)
            
    def _clear_list(self):
        self.entries.clear()
        self.table.setRowCount(0)
        self.detail_text.clear()
        self.lbl_file_count.setText("선택: 0개")
        self._update_status("준비됨")
        
    def _show_about(self):
        QMessageBox.about(self, "정보",
            """<h3>스마트 파일 리네이머 v1.0</h3>
<p>HWP/PDF 파일 분석 및 자동 이름 변경</p>
<hr>
<p>• 2단계 분류 인식 (과학>물리)</p>
<p>• 연번 자동 부여</p>
<p>• 다른 폴더로 복사</p>
<p>• 추출 정보 수동 수정</p>"""
        )


def main():
    import locale
    locale.setlocale(locale.LC_ALL, '')
    
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 9))
    app.setStyle("Fusion")
    
    window = SmartFileRenamer()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
