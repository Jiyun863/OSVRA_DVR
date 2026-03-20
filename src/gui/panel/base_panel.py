"""
Base Panel 클래스 - 모든 패널의 기본 클래스
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QFont


class BasePanel(QWidget):
    """모든 패널의 기본 클래스"""
    
    # 공통 시그널들
    status_changed = pyqtSignal(str)  # 상태 메시지
    data_changed = pyqtSignal()       # 데이터 변경
    
    def __init__(self, title="Panel", collapsible=True):
        super().__init__()
        self.title = title
        self.collapsible = collapsible
        self.is_collapsed = False
        
        self.init_ui()
        self.connect_signals()
    
    def init_ui(self):
        """UI 초기화 - 서브클래스에서 재정의"""
        layout = QVBoxLayout(self)
        # layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 제목 영역
        if self.collapsible:
            self.header_button = QPushButton(f"▼ {self.title}")
            self.header_button.setCheckable(True)
            self.header_button.setChecked(True)
            self.header_button.clicked.connect(self.toggle_collapse)
            self.header_button.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    border: 1px solid #555;
                    background-color: #404040;
                    color: white;
                    padding: 8px;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
                QPushButton:checked {
                    background-color: #606060;
                }
            """)
            layout.addWidget(self.header_button)
        
        # 내용 영역
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # 서브클래스에서 내용 추가
        self.setup_content()
        
        layout.addWidget(self.content_widget)
    
    def setup_content(self):
        """내용 설정 - 서브클래스에서 재정의"""
        pass
    
    def connect_signals(self):
        """시그널 연결 - 서브클래스에서 재정의"""
        pass
    
    def toggle_collapse(self):
        """패널 접기/펼치기"""
        if not self.collapsible:
            return
        
        self.is_collapsed = not self.is_collapsed
        arrow = "▶" if self.is_collapsed else "▼"
        self.header_button.setText(f"{arrow} {self.title}")
        
        if self.is_collapsed:
            self.content_widget.setMaximumHeight(0)
            self.content_widget.setVisible(False)
        else:
            self.content_widget.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.content_widget.setVisible(True)
    
    def set_enabled_state(self, enabled):
        """패널 활성화/비활성화"""
        self.content_widget.setEnabled(enabled)
    
    def emit_status(self, message):
        """상태 메시지 발송"""
        self.status_changed.emit(message)
    
    def create_group_box(self, title, layout_type="vertical"):
        """그룹박스 생성 유틸리티"""
        group_box = QGroupBox(title)
        if layout_type == "vertical":
            layout = QVBoxLayout(group_box)
        else:
            layout = QHBoxLayout(group_box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        return group_box, layout
    
    def create_button_horizontal(self, buttons_config):
        """버튼 행 생성 유틸리티
        buttons_config: [{"text": "버튼명", "callback": 함수, "style": "스타일"}, ...]
        """
        layout = QHBoxLayout()
        layout.setSpacing(5)
        
        buttons = []
        for config in buttons_config:
            button = QPushButton(config["text"])
            if "callback" in config:
                button.clicked.connect(config["callback"])
            if "style" in config:
                button.setStyleSheet(config["style"])
            if "height" in config:
                button.setMinimumHeight(config["height"])
            
            layout.addWidget(button)
            buttons.append(button)
        
        return layout, buttons
    
    def create_button_vertical(self, buttons_config):
        """버튼 행 생성 유틸리티
        buttons_config: [{"text": "버튼명", "callback": 함수, "style": "스타일"}, ...]
        """
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        buttons = []
        for config in buttons_config:
            button = QPushButton(config["text"])
            if "callback" in config:
                button.clicked.connect(config["callback"])
            if "style" in config:
                button.setStyleSheet(config["style"])
            if "height" in config:
                button.setMinimumHeight(config["height"])
            
            layout.addWidget(button)
            buttons.append(button)
        
        return layout, buttons
    
    def disconnect_all_signals(self):
        """모든 시그널 연결 해제"""
        try:
            # 자신의 모든 시그널 연결 해제
            self.disconnect()
            
            # 모든 자식 위젯들의 시그널도 해제
            for child in self.findChildren(QWidget):
                try:
                    child.disconnect()
                except:
                    pass
            
            print(f"✅ {self.__class__.__name__} 시그널 해제 완료")
        except Exception as e:
            print(f"⚠️ {self.__class__.__name__} 시그널 해제 실패: {e}")
    
    def closeEvent(self, event):
        """패널 종료 시 시그널 해제"""
        self.disconnect_all_signals()
        super().closeEvent(event)
    
    def deleteLater(self):
        """Qt 객체 삭제 전 시그널 해제"""
        self.disconnect_all_signals()
        super().deleteLater()


class PanelManager(QObject):
    """패널 매니저 - 모든 패널들을 관리"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.panels = {}
        
        # 공통 데이터 참조
        self.volume_data = None
        self.feature_volume = None
        self.segmentation = None
        self.reconstructed_volume = None
        
    def register_panel(self, name, panel):
        """패널 등록"""
        self.panels[name] = panel
        
        # 공통 시그널 연결
        if hasattr(panel, 'status_changed'):
            panel.status_changed.connect(self.on_status_changed)
        if hasattr(panel, 'data_changed'):
            panel.data_changed.connect(self.on_data_changed)
    
    def get_panel(self, name):
        """패널 가져오기"""
        return self.panels.get(name)
    
    def update_all_panels_data(self):
        """모든 패널의 데이터 업데이트"""
        for panel in self.panels.values():
            if hasattr(panel, 'update_data'):
                panel.update_data(
                    self.volume_data,
                    self.feature_volume,
                    self.segmentation,
                    self.reconstructed_volume
                )
    
    def set_all_panels_enabled(self, enabled):
        """모든 패널 활성화/비활성화"""
        for panel in self.panels.values():
            panel.set_enabled_state(enabled)
    
    def on_status_changed(self, message):
        """패널에서 발송된 상태 메시지 처리"""
        if hasattr(self.main_window, 'statusBar'):
            self.main_window.statusBar().showMessage(message)
    
    def on_data_changed(self):
        """패널에서 발송된 데이터 변경 신호 처리"""
        self.update_all_panels_data()
    
    def save_all_panel_states(self):
        """모든 패널 상태 저장"""
        states = {}
        for name, panel in self.panels.items():
            if hasattr(panel, 'get_state'):
                states[name] = panel.get_state()
        return states
    
    def load_all_panel_states(self, states):
        """모든 패널 상태 로드"""
        for name, state in states.items():
            if name in self.panels and hasattr(self.panels[name], 'set_state'):
                self.panels[name].set_state(state)