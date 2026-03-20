"""
개선된 인터랙티브 Transfer Function 편집 위젯 (완전 수정된 버전)
- 히스토그램 표시 개선
- 클래스별 독립적인 TF 저장/로드
- Global/Class 모드 지원
- ⭐ Global 모드: x축 normalized intensity (0-1)
- ⭐ Class-specific 모드: x축 확률값 (0-1)
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QColorDialog
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor,QLinearGradient, QPainterPath

try:
    from scipy import ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

class TransferFunctionWidget(QWidget):
    """개선된 인터랙티브 Transfer Function 편집 위젯"""
    
    tf_changed = pyqtSignal()
    mode_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        
        # ⭐ [핵심 수정] 고정 너비(600)를 제거하고, 고정 높이만 설정합니다.
        # self.setFixedSize(600, 280)  # <--- 문제의 원인
        self.setFixedHeight(190)    # <--- 수정된 코드
        
        # TF 노드들 (intensity, red, green, blue, alpha)
        self.default_nodes = [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.3, 1.0, 0.5, 0.0, 0.1],
            [0.7, 1.0, 1.0, 1.0, 0.8],
            [1.0, 1.0, 1.0, 1.0, 1.0]
        ]
        self.nodes = [node[:] for node in self.default_nodes]  # 깊은 복사
        
        self.selected_node = -1
        self.dragging = False
        self.node_radius = 8
        
        # 히스토그램 데이터 (개선됨)
        self.histogram = None
        self.histogram_max = 1.0
        self.volume_data = None
        
        # ⭐ 모드 관련 변수
        self.is_class_mode = False  # False: Global (intensity), True: Class-specific (probability)
        self.probability_maps = None  # [H,W,D,C] 확률 맵
        self.current_class_id = 0    # 현재 선택된 클래스
        
        # UI 영역 정의 (개선됨)
        # self.histogram_height = 90  # <--- [삭제] 히스토그램 높이 변수 제거 (더 이상 필요 없음)
        
        # ⭐ 핵심 수정: 모든 UI 요소를 110px (90 + 20) 위로 이동
        # self.tf_area_top = self.histogram_height + 20  #= 110
        self.tf_area_top = 0          # ⭐ TF 편집 영역을 위젯 최상단부터 시작 (0px)
        
        # self.tf_area_height = self.height() - self.tf_area_top - 50  #= 280 - 110 - 50 = 120
        # 수정: 위로 110px 밀어 올려 기존 영역의 높이(120)를 보존하고, 그 위에 110px만큼 확장된 높이를 더함
        self.tf_area_height = self.height() - 50 # ⭐ 새로운 높이: 280 - 50 = 230
        
        # 이제 모든 Y 좌표 계산은 110px 위로 당겨진 효과를 가집니다.
        self.setMouseTracking(True)

        
    def set_volume_data(self, volume_data):
        """볼륨 데이터 설정 및 히스토그램 계산 (균등화 개선)"""
        self.volume_data = volume_data
        if volume_data is not None:
            try:
                data_min, data_max = volume_data.min(), volume_data.max()
                # 데이터 플래튼
                flattened_data = volume_data.flatten()
                # 원본 데이터 그대로 사용
                hist, bin_edges = np.histogram(flattened_data, bins=256, 
                                            range=(data_min, data_max), density=False)
                # 단순한 로그 변환만 적용
                hist = hist.astype(np.float32)
                hist_log = np.log1p(hist)  # log(1 + x)
                if SCIPY_AVAILABLE:
                    hist_final = ndimage.gaussian_filter1d(hist_log, sigma=0.5)
                else:
                    kernel_size = 3
                    kernel = np.ones(kernel_size) / kernel_size
                    hist_final = np.convolve(hist_log, kernel, mode='same')
                
                self.histogram = hist_final
                self.histogram_max = np.max(self.histogram) if np.max(self.histogram) > 0 else 1.0
                self.update()
            except Exception as e:
                print(f"❌ 히스토그램 계산 실패: {e}")
                self.histogram = None

    def set_class_volume_data(self, volume_data, segmentation, class_id):
        """클래스별 볼륨 데이터로 히스토그램 설정 (균등화 적용)"""
        if volume_data is not None and segmentation is not None:
            print(f"📊 클래스 {class_id} 히스토그램 계산 중...")
            try:
                # 해당 클래스의 voxel만 추출
                histogram_volume = volume_data[:,:,:,class_id-1]
                class_mask = (histogram_volume > 0)
                class_voxels = histogram_volume[class_mask]
                
                if len(class_voxels) == 0:
                    print(f"⚠️ 클래스 {class_id}에 해당하는 voxel이 없습니다")
                    self.histogram = None
                    self.update()
                    return
                
                n_bins = 256

                # 히스토그램 계산
                hist, bin_edges = np.histogram(class_voxels, bins=n_bins, 
                                            range=(0, 1), density=False)
                
                # 클래스별 데이터는 더 강한 균등화 적용
                hist = hist.astype(np.float32)
                # 제곱근 변환 (급격한 피크 완화)
                hist_sqrt = np.sqrt(hist + 1)
                # 로그 변환
                hist_log = np.log2(hist_sqrt + 1)
                
                # 가중 평균 스무딩
                window_size = max(3, n_bins // 32)  # 적응적 윈도우 크기
                weights = np.exp(-np.linspace(-1, 1, window_size)**2)  # 가우시안 가중치
                weights /= weights.sum()
                
                hist_final = np.convolve(hist_log, weights, mode='same')
                
                # # 히스토그램 스트레칭
                # hist_min, hist_max = hist_smoothed.min(), hist_smoothed.max()
                # if hist_max > hist_min:
                #     hist_final = (hist_smoothed - hist_min) / (hist_max - hist_min)
                #     hist_final = hist_final * 80  # 0-80 범위로 스케일링
                # else:
                #     hist_final = hist_smoothed
                
                # 256 bins로 확장
                if len(hist_final) != 256:
                    x_old = np.linspace(0, 1, len(hist_final))
                    x_new = np.linspace(0, 1, 256)
                    
                    # 보간 방식 선택 (데이터 크기에 따라)
                    if len(hist_final) >= 64:
                        interp_kind = 'cubic'
                    else:
                        interp_kind = 'linear'
                    
                    try:
                        from scipy.interpolate import interp1d
                        f = interp1d(x_old, hist_final, kind=interp_kind, fill_value='extrapolate')
                        hist_final = f(x_new)
                    except ImportError:
                        # scipy 없으면 선형 보간
                        hist_final = np.interp(x_new, x_old, hist_final)
                
                self.histogram = hist_final
                self.histogram_max = np.max(self.histogram) if np.max(self.histogram) > 0 else 1.0
                
                print(f"   히스토그램 최대값 (균등화 후): {self.histogram_max:.2f}")
                print(f"   사용된 bins: {n_bins} -> 256 (보간)")
                
                self.update()
            except Exception as e:
                print(f"❌ 클래스 {class_id} 히스토그램 계산 실패: {e}")
                self.histogram = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. 배경 (전체 위젯)
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        
        # 2. 그리드 그리기 (TF 영역)
        
        # 3. ⭐ TF 영역에 맞춘 히스토그램 그리기 (배경처럼)
        self.draw_tf_area_histogram(painter)
        self.draw_enhanced_grid(painter)

        
        # 4. TF 곡선 그리기 (히스토그램 위에 겹쳐짐)
        self.draw_enhanced_tf_curve(painter)
        
        # 5. 노드 그리기
        self.draw_nodes(painter)
        
        # 6. 색상 바
        self.draw_enhanced_color_bar(painter)
    
    def draw_tf_area_histogram(self, painter):
        if self.histogram is None:
            # 히스토그램이 없는 경우, TF 영역 배경을 그립니다.
            painter.fillRect(0, self.tf_area_top, self.width(), self.tf_area_height, QColor(50, 50, 50))
            return

        # 배경 (TF 영역)
        painter.fillRect(0, self.tf_area_top, self.width(), self.tf_area_height, QColor(50, 50, 50))

        # ⭐ TF 영역 높이를 사용합니다.
        max_height = self.tf_area_height
        bin_width = self.width() / len(self.histogram)
        
        # Path로 곡선 만들기
        path = QPainterPath()
        # 시작: (0, TF 영역의 바닥)
        path.moveTo(0, self.tf_area_top + max_height)

        for i, count in enumerate(self.histogram):
            x = int(i * bin_width)
            # count / self.histogram_max : 0 ~ 1 사이의 정규화된 높이
            height = int((count / self.histogram_max) * max_height)
            # y: (TF 영역 바닥) - height
            y = self.tf_area_top + max_height - height 
            path.lineTo(x, y)

        # 마지막: (width, TF 영역의 바닥)
        path.lineTo(self.width(), self.tf_area_top + max_height)
        path.closeSubpath()

        # 채우기 색 (반투명) - 색상 변경: 좀 더 배경같은 느낌으로
        brush = QBrush(QColor(150, 50, 50, 100)) # 빨강 + 투명도 (더 연하게)
        painter.fillPath(path, brush)

        # 외곽선
        painter.setPen(QPen(QColor(200, 50, 50, 180), 1)) # 외곽선도 연하게
        painter.drawPath(path)

        # TF 영역 테두리
        painter.setPen(QPen(QColor(120, 120, 120), 1))
        painter.drawRect(0, self.tf_area_top, self.width() - 1, self.tf_area_height)

    def draw_enhanced_grid(self, painter):
        painter.setPen(QPen(QColor(80, 80, 80), 1, Qt.PenStyle.DotLine))
        
        # 세로 그리드
        for i in range(0, 11):
            x = int((i / 10.0) * self.width())
            painter.drawLine(x, self.tf_area_top, x, self.height() - 40)
        
        # 가로 그리드
        for i in range(0, 6):
            y = int(self.tf_area_top + (i / 5.0) * self.tf_area_height)
            painter.drawLine(0, y, self.width(), y)
        
        # ⭐ 축 레이블 (모드에 따라 다름)
        painter.setPen(QPen(QColor(180, 180, 180), 1))
    
    def draw_enhanced_tf_curve(self, painter):
        """간단한 TF 곡선 그리기"""
        if len(self.nodes) < 2:
            return
        # 알파 곡선 (간단하게)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        points = []
        
        for x in range(self.width()):
            # ⭐ 모드에 관계없이 x축은 0-1로 정규화 (노드 좌표계)
            intensity = x / (self.width() - 1)
            alpha = self.interpolate_alpha(intensity)
            y = int((1 - alpha) * self.tf_area_height + self.tf_area_top)
            points.append(QPoint(x, y))
        
        if len(points) > 1:
            painter.drawPolyline(points)
    
    def draw_enhanced_color_bar(self, painter):
        """수정된 색상 바 그리기 (그라디언트 수정)"""
        bar_height = 25
        bar_y = self.height() - bar_height - 5
        
        # QLinearGradient를 사용한 부드러운 그라디언트
        from PyQt6.QtGui import QLinearGradient, QBrush
        
        gradient = QLinearGradient(0, bar_y, self.width(), bar_y)
        
        # 노드 기반으로 그라디언트 생성
        sorted_nodes = sorted(self.nodes, key=lambda x: x[0])
        
        for node in sorted_nodes:
            intensity = node[0]  # 0-1 범위
            r, g, b = node[1], node[2], node[3]
            alpha = node[4]
            
            # RGB 값 범위 확인
            r = max(0, min(1, r))
            g = max(0, min(1, g)) 
            b = max(0, min(1, b))
            alpha = max(0, min(1, alpha))
            
            # 배경과 블렌딩 (체커보드 패턴 배경 시뮬레이션)
            bg_r, bg_g, bg_b = 50, 50, 50  # 어두운 배경
            
            # 알파 블렌딩
            final_r = int(r * 255 * alpha + bg_r * (1 - alpha))
            final_g = int(g * 255 * alpha + bg_g * (1 - alpha))
            final_b = int(b * 255 * alpha + bg_b * (1 - alpha))
            
            color = QColor(final_r, final_g, final_b)
            gradient.setColorAt(intensity, color)
        
        # 그라디언트로 배경 칠하기
        painter.fillRect(0, bar_y, self.width(), bar_height, QBrush(gradient))
        
        # 투명도 패턴 오버레이 (체커보드 효과)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        checker_size = 8
        for x in range(0, self.width(), checker_size * 2):
            for y in range(bar_y, bar_y + bar_height, checker_size):
                if ((x // checker_size) + (y // checker_size)) % 2 == 0:
                    painter.fillRect(x, y, checker_size, checker_size, 
                                QColor(255, 255, 255, 15))
    
    def draw_nodes(self, painter):
        """간단한 노드 그리기"""
        for i, node in enumerate(self.nodes):
            x = int(node[0] * (self.width() - 1))
            y = int((1 - node[4]) * self.tf_area_height + self.tf_area_top)
            
            # 노드 색상
            color = QColor(int(node[1]*255), int(node[2]*255), int(node[3]*255))
            
            # 선택된 노드 표시
            if i == self.selected_node:
                painter.setPen(QPen(QColor(255, 255, 0), 3))
                painter.setBrush(QBrush(color))
            else:
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.setBrush(QBrush(color))
            
            painter.drawEllipse(x - self.node_radius, y - self.node_radius, 
                            2 * self.node_radius, 2 * self.node_radius)
    
    def interpolate_alpha(self, intensity):
        """알파값 보간"""
        return self.interpolate_value(intensity, 4)
    
    def interpolate_color(self, intensity):
        """RGB 색상 보간"""
        r = self.interpolate_value(intensity, 1)
        g = self.interpolate_value(intensity, 2) 
        b = self.interpolate_value(intensity, 3)
        return [r, g, b]
    
    def interpolate_value(self, intensity, channel):
        """특정 채널의 값 보간"""
        if len(self.nodes) < 2:
            return 0.0
        
        # 정렬된 노드 찾기
        sorted_nodes = sorted(self.nodes, key=lambda x: x[0])
        
        if intensity <= sorted_nodes[0][0]:
            return sorted_nodes[0][channel]
        if intensity >= sorted_nodes[-1][0]:
            return sorted_nodes[-1][channel]
        
        # 두 노드 사이 보간
        for i in range(len(sorted_nodes) - 1):
            if sorted_nodes[i][0] <= intensity <= sorted_nodes[i+1][0]:
                t = (intensity - sorted_nodes[i][0]) / (sorted_nodes[i+1][0] - sorted_nodes[i][0])
                return sorted_nodes[i][channel] * (1-t) + sorted_nodes[i+1][channel] * t
        
        return 0.0
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected_node = self.find_node_at_pos(event.position())
            if self.selected_node >= 0:
                self.dragging = True
                print(f"🎯 노드 {self.selected_node} 선택")
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # 우클릭으로 색상 변경
            node_idx = self.find_node_at_pos(event.position())
            if node_idx >= 0:
                self.change_node_color(node_idx)
    
    def mouseMoveEvent(self, event):
        if self.dragging and self.selected_node >= 0:
            # 노드 위치 업데이트
            x = max(0, min(event.position().x(), self.width() - 1))
            y = max(self.tf_area_top, min(event.position().y(), self.height() - 50))
            
            intensity = x / (self.width() - 1)
            alpha = 1 - (y - self.tf_area_top) / self.tf_area_height
            
            # 이웃 노드와 겹치지 않도록 제한
            sorted_nodes = sorted(enumerate(self.nodes), key=lambda x: x[1][0])
            current_pos = None
            for i, (orig_idx, node) in enumerate(sorted_nodes):
                if orig_idx == self.selected_node:
                    current_pos = i
                    break
            
            if current_pos is not None:
                min_intensity = 0.0
                max_intensity = 1.0
                
                # 이웃 노드와의 최소 거리 유지
                if current_pos > 0:
                    min_intensity = max(0.0, sorted_nodes[current_pos - 1][1][0] + 0.01)
                if current_pos < len(sorted_nodes) - 1:
                    max_intensity = min(1.0, sorted_nodes[current_pos + 1][1][0] - 0.01)
                
                intensity = max(min_intensity, min(max_intensity, intensity))
            
            self.nodes[self.selected_node][0] = intensity
            self.nodes[self.selected_node][4] = max(0, min(1, alpha))
            
            self.update()
            self.tf_changed.emit()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False

    def mouseDoubleClickEvent(self, event):
        """더블클릭으로 노드 삭제 또는 추가"""
        if event.button() == Qt.MouseButton.LeftButton:
            node_idx = self.find_node_at_pos(event.position())
            
            if node_idx >= 0:
                # 노드 위에서 더블클릭 = 삭제
                if len(self.nodes) > 2:  # 최소 2개 노드 유지
                    print(f"🗑️ 노드 {node_idx} 삭제 (더블클릭)")
                    del self.nodes[node_idx]
                    self.selected_node = -1
                    self.update()
                    self.tf_changed.emit()
                else:
                    print("⚠️ 최소 2개 노드는 유지해야 합니다")
            elif (event.position().y() >= self.tf_area_top and
                event.position().y() <= self.tf_area_top + self.tf_area_height):
                # 빈 공간에서 더블클릭 = 새 노드 추가 (기존 코드)
                x = event.position().x()
                y = event.position().y()
                
                intensity = x / (self.width() - 1)
                alpha = 1 - (y - self.tf_area_top) / self.tf_area_height
                
                # 현재 위치에서의 색상 보간
                current_color = self.interpolate_color(intensity)
                
                # 새 노드 추가
                new_node = [intensity, current_color[0], current_color[1], current_color[2], max(0, min(1, alpha))]
                self.nodes.append(new_node)
                self.nodes.sort(key=lambda x: x[0])
                
                print(f"➕ 새 노드 추가: intensity={intensity:.2f}, alpha={alpha:.2f}")
                
                self.update()
                self.tf_changed.emit()
    
    def change_node_color(self, node_idx):
        """노드 색상 변경"""
        if 0 <= node_idx < len(self.nodes):
            current_color = QColor(
                int(self.nodes[node_idx][1] * 255),
                int(self.nodes[node_idx][2] * 255),
                int(self.nodes[node_idx][3] * 255)
            )
            
            color = QColorDialog.getColor(current_color, self, f"노드 {node_idx} 색상 선택")
            
            if color.isValid():
                self.nodes[node_idx][1] = color.red() / 255.0
                self.nodes[node_idx][2] = color.green() / 255.0
                self.nodes[node_idx][3] = color.blue() / 255.0
                
                print(f"🎨 노드 {node_idx} 색상 변경: RGB({color.red()}, {color.green()}, {color.blue()})")
                
                self.update()
                self.tf_changed.emit()
    
    def find_node_at_pos(self, pos):
        """특정 위치의 노드 찾기"""
        for i, node in enumerate(self.nodes):
            x = node[0] * (self.width() - 1)
            y = (1 - node[4]) * self.tf_area_height + self.tf_area_top
            
            if (pos.x() - x)**2 + (pos.y() - y)**2 <= self.node_radius**2:
                return i
        return -1
    
    def reset_to_default(self):
        """기본 노드로 초기화"""
        self.nodes = [node[:] for node in self.default_nodes]
        self.selected_node = -1
        self.update()
        self.tf_changed.emit()
        print("🔄 Transfer Function 기본값으로 초기화")
    
    def get_nodes(self):
        """노드의 깊은 복사 반환"""
        return [node[:] for node in self.nodes]
    
    def set_transfer_function_from_array(self, tf_array):
        """TF 배열에서 노드 생성하여 설정"""
        if tf_array is None or len(tf_array) == 0:
            return
        # 기존 노드 클리어
        self.nodes = tf_array

        # 최소 2개 노드 보장
        if len(self.nodes) < 2:
            self.nodes = [node[:] for node in self.default_nodes]
        
        self.selected_node = -1
        self.update()
        print(f"📥 TF 배열에서 {len(self.nodes)}개 노드 생성")

    def apply_class_color(self, class_id):
        """클래스별 기본 색상 적용"""
        class_colors = [
            [0.8, 0.2, 0.2],  # Class 0: 빨강
            [0.2, 0.8, 0.2],  # Class 1: 초록
            [0.2, 0.2, 0.8],  # Class 2: 파랑
            [0.8, 0.8, 0.2],  # Class 3: 노랑
            [0.8, 0.2, 0.8],  # Class 4: 마젠타
            [0.2, 0.8, 0.8],  # Class 5: 시안
            [0.6, 0.3, 0.1],  # Class 6: 브라운
            [0.9, 0.5, 0.1],  # Class 7: 오렌지
            [0.5, 0.5, 0.5],  # Class 8: 그레이
            [0.3, 0.3, 0.0],  # Class 9: 올리브
            [0.6, 0.0, 0.6],  # Class 10: 퍼플
            [0.0, 0.6, 0.6],  # Class 11: 틸
            [0.4, 0.7, 0.1],  # Class 12: 라임
            [0.7, 0.1, 0.4],  # Class 13: 핑크레드
            [0.1, 0.4, 0.7],  # Class 14: 블루그린
            [0.9, 0.7, 0.3],  # Class 15: 라이트 옐로우
            [0.3, 0.9, 0.7],  # Class 16: 아쿠아
            [0.7, 0.3, 0.9],  # Class 17: 라벤더
            [0.9, 0.3, 0.5],  # Class 18: 로즈
            [0.5, 0.9, 0.3],  # Class 19: 연두
        ]

        array_index = class_id - 1
        if 0 <= array_index < len(class_colors):
            color = class_colors[array_index]
            
            # 모든 노드에 해당 색상 적용
            for node in self.nodes:
                node[1] = color[0]  # R
                node[2] = color[1]  # G
                node[3] = color[2]  # B
            
            self.update()
            self.tf_changed.emit()
            print(f"🎨 클래스 {array_index} 색상 적용: RGB({color[0]:.1f}, {color[1]:.1f}, {color[2]:.1f})")

    def get_opacity_lut(self):
        """현재 TF의 Opacity Lookup Table (256 크기) 반환"""
        lut = np.zeros(256, dtype=np.float32)
        for i in range(256):
            intensity = i / 255.0
            alpha = self.interpolate_alpha(intensity)
            lut[i] = alpha
        
        return lut
