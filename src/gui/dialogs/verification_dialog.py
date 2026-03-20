import numpy as np
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

class PointVerificationDialog(QDialog):
    """
    선택된 3D 점이 정확한 해부학적 위치(예: 신경)에 있는지 검증하기 위한 MPR 뷰어
    """
    def __init__(self, volume_data, point_3d, voxel_spacing, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Point Verification (MPR View)")
        self.resize(1000, 400)
        
        self.volume = volume_data
        self.point = point_3d  # (x, y, z) physical coord
        self.spacing = voxel_spacing
        
        # UI Setup
        layout = QHBoxLayout()
        self.setLayout(layout)
        
        # Canvas
        self.figure = Figure(figsize=(12, 4))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        self.plot_slices()

    def plot_slices(self):
        # 1. Physical Coordinate -> Voxel Index 변환
        # Spacing도 (sx, sy, sz) 순서라고 가정
        idx_x = int(self.point[0] / self.spacing[0])
        idx_y = int(self.point[1] / self.spacing[1])
        idx_z = int(self.point[2] / self.spacing[2])
        
        # 데이터 shape: (Width=x, Height=y, Depth=z)
        w, h, d = self.volume.shape
        
        # 범위 안전 장치
        idx_x = np.clip(idx_x, 0, w-1)
        idx_y = np.clip(idx_y, 0, h-1)
        idx_z = np.clip(idx_z, 0, d-1)
        
        # ---------------------------------------------------------
        # [중요] 슬라이스 추출 및 Transpose (Visual Orientation 보정)
        # imshow는 (Height, Width) 즉 (세로, 가로) 순서를 원함
        # ---------------------------------------------------------

        # 1. Axial (Top View): XY 평면
        # volume[:, :, z] -> (x, y) 형태. 
        # 화면: 세로가 y, 가로가 x여야 함 -> (y, x)로 Transpose 필요
        slice_axial = self.volume[:, :, idx_z].T 
        
        # 2. Coronal (Front View): XZ 평면
        # volume[:, y, :] -> (x, z) 형태.
        # 화면: 세로가 z(키), 가로가 x(너비)여야 함 -> (z, x)로 Transpose 필요
        slice_coronal = self.volume[:, idx_y, :].T
        
        # 3. Sagittal (Side View): YZ 평면
        # volume[x, :, :] -> (y, z) 형태.
        # 화면: 세로가 z(키), 가로가 y(깊이)여야 함 -> (z, y)로 Transpose 필요
        slice_sagittal = self.volume[idx_x, :, :].T
        
        # ---------------------------------------------------------
        # Plotting
        # ---------------------------------------------------------
        self.figure.clear() # 기존 그림 지우기

        # [View 1] Axial (XY)
        ax1 = self.figure.add_subplot(131)
        # origin='lower': 인덱스 0이 바닥(y=0)에 옴
        ax1.imshow(slice_axial, cmap='gray', origin='lower', aspect='equal')
        # Transpose 했으므로 axhline은 y좌표(Row), axvline은 x좌표(Col)
        ax1.axhline(idx_y, color='r', linestyle='--', linewidth=1) 
        ax1.axvline(idx_x, color='r', linestyle='--', linewidth=1)
        ax1.set_title(f"Axial (Z={idx_z})\nTop View")
        ax1.axis('off')
        
        # [View 2] Coronal (XZ)
        ax2 = self.figure.add_subplot(132)
        # Aspect Ratio: Pixel Height(z) / Pixel Width(x)
        aspect_cor = self.spacing[2] / self.spacing[0]
        ax2.imshow(slice_coronal, cmap='gray', origin='lower', aspect=aspect_cor)
        ax2.axhline(idx_z, color='r', linestyle='--', linewidth=1) # 세로축(Z)
        ax2.axvline(idx_x, color='r', linestyle='--', linewidth=1) # 가로축(X)
        ax2.set_title(f"Coronal (Y={idx_y})\nFront View")
        ax2.axis('off')

        # [View 3] Sagittal (YZ)
        ax3 = self.figure.add_subplot(133)
        # Aspect Ratio: Pixel Height(z) / Pixel Width(y)
        aspect_sag = self.spacing[2] / self.spacing[1]
        ax3.imshow(slice_sagittal, cmap='gray', origin='lower', aspect=aspect_sag)
        ax3.axhline(idx_z, color='r', linestyle='--', linewidth=1) # 세로축(Z)
        ax3.axvline(idx_y, color='r', linestyle='--', linewidth=1) # 가로축(Y)
        ax3.set_title(f"Sagittal (X={idx_x})\nSide View")
        ax3.axis('off')

        self.figure.tight_layout()
        self.canvas.draw()