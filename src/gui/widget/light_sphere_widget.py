"""
3D 구형 라이트 위치 조정 위젯
"""
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor

class LightSphereWidget(QWidget):
    """3D 구형 라이트 위치 조정 위젯"""
    
    light_changed = pyqtSignal(float, float, float)
    
    def __init__(self):
        super().__init__()
        self.setFixedSize(100, 100)
        self.setMouseTracking(True)
        
        # 구면 좌표계 (theta: 수평각, phi: 수직각, radius: 거리)
        self.theta = 45.0  # 수평각 (도)
        self.phi = 45.0    # 수직각 (도) 
        self.radius = 2.0  # 거리
        
        self.dragging = False
        
    def spherical_to_cartesian(self):
        """구면 좌표를 직교 좌표로 변환"""
        theta_rad = np.radians(self.theta)
        phi_rad = np.radians(self.phi)
        
        x = self.radius * np.sin(phi_rad) * np.cos(theta_rad)
        y = self.radius * np.sin(phi_rad) * np.sin(theta_rad)  
        z = self.radius * np.cos(phi_rad)
        
        return x, y, z
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 배경 원 그리기
        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 5
        
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.drawEllipse(center.x() - radius, center.y() - radius, 
                          radius * 2, radius * 2)
        
        # 라이트 위치 표시 (2D 투영) - phi 각도 반영
        phi_factor = np.sin(np.radians(self.phi))  # phi=0이면 가운데, phi=90이면 가장자리
        light_x = center.x() + radius * np.cos(np.radians(self.theta)) * phi_factor
        light_y = center.y() + radius * np.sin(np.radians(self.theta)) * phi_factor
        
        painter.setPen(QPen(QColor(255, 255, 0), 3))
        painter.setBrush(QBrush(QColor(255, 255, 100)))
        painter.drawEllipse(int(light_x - 5), int(light_y - 5), 10, 10)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.update_light_position(event.position())
            
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.update_light_position(event.position())
            
    def mouseReleaseEvent(self, event):
        self.dragging = False
        
    def update_light_position(self, pos):
        """마우스 위치에서 라이트 위치 업데이트"""
        center = self.rect().center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        
        # 각도 계산
        self.theta = np.degrees(np.arctan2(dy, dx))
        
        # 거리 계산 (phi 각도로 변환)
        distance = np.sqrt(dx*dx + dy*dy)
        max_distance = min(self.width(), self.height()) // 2 - 5
        normalized_distance = min(distance / max_distance, 1.0)
        self.phi = normalized_distance * 90  # 0-90도 범위 (가운데=정면, 가장자리=옆면)
        
        # 직교 좌표로 변환하여 시그널 발송
        x, y, z = self.spherical_to_cartesian()
        self.light_changed.emit(x, y, z)
        
        self.update()