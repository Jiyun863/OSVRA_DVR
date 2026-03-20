"""
Phase 1: SOI (Slice of Interest) Plane 정의 및 PET reslice
축정렬 SOI plane을 물리적으로 정의하고, 각 픽셀의 world 좌표를 생성
"""

import numpy as np
from dataclasses import dataclass, field


@dataclass
class SOIPlane:
    """Slice of Interest 물리적 정의"""
    origin: np.ndarray          # (3,) plane 중심점 world 좌표 (mm)
    normal: np.ndarray          # (3,) plane 법선 벡터 (정규화)
    u_axis: np.ndarray          # (3,) plane 내 수평 축
    v_axis: np.ndarray          # (3,) plane 내 수직 축
    resolution: tuple           # (height, width) pixel 수
    pixel_spacing: tuple        # (du, dv) mm per pixel
    pet_slice: np.ndarray       # (height, width) PET SOI 이미지
    axis_name: str              # "Axial" | "Coronal" | "Sagittal"
    slice_index: int            # 볼륨 내 슬라이스 인덱스
    _ray_start_cache: np.ndarray = field(default=None, repr=False)

    def get_ray_start_points(self) -> np.ndarray:
        """SOI plane 각 픽셀의 world 좌표 반환

        Returns:
            (H, W, 3) array of world coordinates
        """
        if self._ray_start_cache is not None:
            return self._ray_start_cache

        H, W = self.resolution
        du, dv = self.pixel_spacing

        # pixel grid centered on origin
        u_indices = np.arange(W, dtype=np.float64) - W / 2.0 + 0.5
        v_indices = np.arange(H, dtype=np.float64) - H / 2.0 + 0.5

        # (H, W) grids
        u_grid, v_grid = np.meshgrid(u_indices, v_indices)

        # (H, W, 3) world positions
        points = (
            self.origin[np.newaxis, np.newaxis, :]
            + u_grid[:, :, np.newaxis] * du * self.u_axis[np.newaxis, np.newaxis, :]
            + v_grid[:, :, np.newaxis] * dv * self.v_axis[np.newaxis, np.newaxis, :]
        )

        self._ray_start_cache = points.astype(np.float64)
        return self._ray_start_cache


class SOIPlaneBuilder:
    """SOI plane 생성기"""

    # 축 이름 -> numpy axis 인덱스 (볼륨 shape (X, Y, Z) 기준)
    _AXIS_MAP = {
        "Axial": 2,     # Z 축 슬라이싱
        "Coronal": 1,   # Y 축 슬라이싱
        "Sagittal": 0,  # X 축 슬라이싱
    }

    @staticmethod
    def build_axis_aligned(
        axis_name: str,
        slice_index: int,
        pet_volume: np.ndarray,
        pet_spacing: tuple,
        ct_volume: np.ndarray = None,
        ct_spacing: tuple = None,
    ) -> SOIPlane:
        """축정렬 SOI plane 생성

        Args:
            axis_name: "Axial" | "Coronal" | "Sagittal"
            slice_index: 볼륨 내 슬라이스 인덱스
            pet_volume: (X, Y, Z) PET volume
            pet_spacing: (sx, sy, sz) mm per voxel
            ct_volume: (X, Y, Z) CT volume (해상도 기준용, optional)
            ct_spacing: (sx, sy, sz) CT spacing (optional)

        Returns:
            SOIPlane instance
        """
        sx, sy, sz = pet_spacing
        X, Y, Z = pet_volume.shape

        # 볼륨 물리적 중심
        center = np.array([
            (X - 1) * sx / 2.0,
            (Y - 1) * sy / 2.0,
            (Z - 1) * sz / 2.0,
        ])

        if axis_name == "Axial":
            # Z축 슬라이싱
            idx = min(max(slice_index, 0), Z - 1)
            origin = np.array([center[0], center[1], idx * sz])
            normal = np.array([0.0, 0.0, 1.0])
            u_axis = np.array([1.0, 0.0, 0.0])
            v_axis = np.array([0.0, 1.0, 0.0])
            resolution = (Y, X)  # (height, width)
            pixel_spacing = (sy, sx)
            pet_slice = pet_volume[:, :, idx].T  # (X,Y) -> (Y,X)

        elif axis_name == "Coronal":
            # Y축 슬라이싱
            idx = min(max(slice_index, 0), Y - 1)
            origin = np.array([center[0], idx * sy, center[2]])
            normal = np.array([0.0, 1.0, 0.0])
            u_axis = np.array([1.0, 0.0, 0.0])
            v_axis = np.array([0.0, 0.0, 1.0])
            resolution = (Z, X)  # (height, width)
            pixel_spacing = (sz, sx)
            pet_slice = pet_volume[:, idx, :].T  # (X,Z) -> (Z,X)

        elif axis_name == "Sagittal":
            # X축 슬라이싱
            idx = min(max(slice_index, 0), X - 1)
            origin = np.array([idx * sx, center[1], center[2]])
            normal = np.array([1.0, 0.0, 0.0])
            u_axis = np.array([0.0, 1.0, 0.0])
            v_axis = np.array([0.0, 0.0, 1.0])
            resolution = (Z, Y)  # (height, width)
            pixel_spacing = (sz, sy)
            pet_slice = pet_volume[idx, :, :]  # (Y,Z)

        else:
            raise ValueError(f"Unknown axis: {axis_name}")

        return SOIPlane(
            origin=origin,
            normal=normal,
            u_axis=u_axis,
            v_axis=v_axis,
            resolution=resolution,
            pixel_spacing=pixel_spacing,
            pet_slice=pet_slice.astype(np.float32),
            axis_name=axis_name,
            slice_index=idx,
        )
