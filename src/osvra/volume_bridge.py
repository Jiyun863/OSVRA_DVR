"""
Phase 0: Volume Bridge — PET/CT 좌표계 통합 유틸리티
VTK↔NumPy 좌표 변환, 리샘플링, trilinear interpolation, view direction 계산
"""

import numpy as np
from scipy.ndimage import map_coordinates, zoom


class VolumeBridge:
    """PET/CT 좌표계 통합 유틸리티"""

    @staticmethod
    def voxel_to_world(voxel_ijk, origin, spacing, direction=None):
        """(i,j,k) voxel index -> (x,y,z) world coordinate (mm)

        Args:
            voxel_ijk: (N, 3) or (3,) voxel indices
            origin: (3,) world origin
            spacing: (3,) voxel spacing in mm
            direction: (3,3) direction cosine matrix (identity if None)

        Returns:
            (N, 3) or (3,) world coordinates in mm
        """
        voxel_ijk = np.asarray(voxel_ijk, dtype=np.float64)
        origin = np.asarray(origin, dtype=np.float64)
        spacing = np.asarray(spacing, dtype=np.float64)

        scaled = voxel_ijk * spacing
        if direction is not None:
            direction = np.asarray(direction, dtype=np.float64)
            if scaled.ndim == 1:
                return origin + direction @ scaled
            else:
                return origin + (direction @ scaled.T).T
        else:
            return origin + scaled

    @staticmethod
    def world_to_voxel(world_xyz, origin, spacing, direction=None):
        """(x,y,z) world coordinate -> (i,j,k) voxel index (float)

        Args:
            world_xyz: (N, 3) or (3,) world coordinates in mm
            origin: (3,) world origin
            spacing: (3,) voxel spacing in mm
            direction: (3,3) direction cosine matrix (identity if None)

        Returns:
            (N, 3) or (3,) voxel indices (float, for interpolation)
        """
        world_xyz = np.asarray(world_xyz, dtype=np.float64)
        origin = np.asarray(origin, dtype=np.float64)
        spacing = np.asarray(spacing, dtype=np.float64)

        shifted = world_xyz - origin
        if direction is not None:
            direction = np.asarray(direction, dtype=np.float64)
            inv_dir = np.linalg.inv(direction)
            if shifted.ndim == 1:
                shifted = inv_dir @ shifted
            else:
                shifted = (inv_dir @ shifted.T).T

        return shifted / spacing

    @staticmethod
    def resample_to_reference(source_vol, source_spacing, ref_shape, ref_spacing, order=1):
        """source 볼륨을 reference 격자로 리샘플링

        Args:
            source_vol: (X, Y, Z) source volume
            source_spacing: (3,) source voxel spacing
            ref_shape: (3,) target shape
            ref_spacing: (3,) target voxel spacing
            order: interpolation order (1=linear)

        Returns:
            resampled volume with shape ref_shape
        """
        source_spacing = np.asarray(source_spacing, dtype=np.float64)
        ref_spacing = np.asarray(ref_spacing, dtype=np.float64)

        zoom_factors = (
            np.array(source_vol.shape) * source_spacing
        ) / (np.array(ref_shape) * ref_spacing)

        # zoom to match ref_shape
        actual_zoom = np.array(ref_shape) / np.array(source_vol.shape)
        resampled = zoom(source_vol, actual_zoom, order=order, mode='nearest')

        return resampled

    @staticmethod
    def trilinear_interpolate(volume, positions_voxel):
        """연속 voxel 좌표에서 trilinear interpolation

        Args:
            volume: (X, Y, Z) 3D volume
            positions_voxel: (N, 3) or (3,) continuous voxel coordinates

        Returns:
            (N,) or scalar interpolated values
        """
        positions_voxel = np.asarray(positions_voxel, dtype=np.float64)
        if positions_voxel.ndim == 1:
            coords = positions_voxel.reshape(3, 1)
        else:
            coords = positions_voxel.T

        result = map_coordinates(volume, coords, order=1, mode='nearest')
        return result

    @staticmethod
    def build_tf_luts(tf_nodes):
        """TF 노드 → (opacity_lut_256, color_lut_256x3)

        Args:
            tf_nodes: [[pos, r, g, b, alpha], ...]

        Returns:
            opacity_lut: (256,) float32
            color_lut: (256, 3) float32
        """
        if not tf_nodes or len(tf_nodes) < 2:
            return np.zeros(256, dtype=np.float32), np.zeros((256, 3), dtype=np.float32)

        sorted_nodes = sorted(tf_nodes, key=lambda x: x[0])
        positions = [n[0] for n in sorted_nodes]
        alphas = [n[4] for n in sorted_nodes]
        reds = [n[1] for n in sorted_nodes]
        greens = [n[2] for n in sorted_nodes]
        blues = [n[3] for n in sorted_nodes]

        x = np.linspace(0, 1, 256)
        opacity_lut = np.interp(x, positions, alphas).astype(np.float32)
        color_lut = np.column_stack([
            np.interp(x, positions, reds),
            np.interp(x, positions, greens),
            np.interp(x, positions, blues),
        ]).astype(np.float32)

        return opacity_lut, color_lut

    @staticmethod
    def get_view_direction(camera):
        """vtkCamera -> 정규화된 view direction 벡터

        Args:
            camera: vtkCamera instance

        Returns:
            (3,) normalized direction vector (camera -> focal point)
        """
        pos = np.array(camera.GetPosition())
        focal = np.array(camera.GetFocalPoint())
        direction = focal - pos
        norm = np.linalg.norm(direction)
        if norm < 1e-12:
            return np.array([0.0, 0.0, -1.0])
        return direction / norm
