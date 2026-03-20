"""
PET SOI Volume Renderer
Camera→SOI 방향 front-to-back compositing (logistic weight 없음)
"""

import numpy as np
from scipy.ndimage import map_coordinates
from src.osvra.volume_bridge import VolumeBridge


class PETSliceRenderer:
    """Camera→SOI 방향 PET 볼륨 렌더링 (vectorized front-to-back)"""

    def __init__(
        self,
        pet_volume: np.ndarray,
        pet_spacing: tuple,
        pet_tf_nodes: list,
        sample_step_mm: float = 1.0,
        max_distance_mm: float = 500.0,
    ):
        """
        Args:
            pet_volume: (X, Y, Z) normalized [0, 1]
            pet_spacing: (sx, sy, sz) mm
            pet_tf_nodes: [[pos, r, g, b, alpha], ...]
            sample_step_mm: ray marching step size in mm
            max_distance_mm: maximum ray distance from SOI toward camera
        """
        self.pet_volume = pet_volume
        self.pet_spacing = np.array(pet_spacing, dtype=np.float64)
        self.opacity_lut, self.color_lut = VolumeBridge.build_tf_luts(pet_tf_nodes)
        self.sample_step = sample_step_mm
        self.max_distance = max_distance_mm

    def render(self, soi_plane, view_direction: np.ndarray) -> np.ndarray:
        """Vectorized front-to-back PET volume rendering (camera→SOI)

        All N=H*W rays are processed simultaneously per step.

        Args:
            soi_plane: SOIPlane instance
            view_direction: (3,) normalized camera->focal direction

        Returns:
            pet_rgba: (H, W, 4) RGBA float [0, 1]
        """
        H, W = soi_plane.resolution
        N = H * W

        # Ray direction: camera → SOI (양의 view 방향)
        ray_dir = np.asarray(view_direction, dtype=np.float64)
        ray_dir = ray_dir / np.linalg.norm(ray_dir)
        step_vec = ray_dir * self.sample_step  # (3,)
        max_steps = int(self.max_distance / self.sample_step)

        # SOI plane 픽셀 world 좌표 → camera 쪽으로 max_distance만큼 후퇴하여 시작
        soi_pixels = soi_plane.get_ray_start_points()  # (H, W, 3)
        ray_starts = soi_pixels - self.max_distance * ray_dir  # (H, W, 3)

        shape = self.pet_volume.shape
        shape_arr = np.array(shape, dtype=np.float64) - 1
        inv_spacing = 1.0 / self.pet_spacing  # world→voxel

        # Flatten rays
        positions = ray_starts.reshape(N, 3).copy()  # (N, 3)

        # Accumulators (front-to-back)
        r_acc = np.zeros(N, dtype=np.float32)
        g_acc = np.zeros(N, dtype=np.float32)
        b_acc = np.zeros(N, dtype=np.float32)
        a_acc = np.zeros(N, dtype=np.float32)

        active = np.ones(N, dtype=bool)
        TERM_CHECK_INTERVAL = 10

        for step in range(max_steps):
            if not np.any(active):
                break

            if step > 0 and step % TERM_CHECK_INTERVAL == 0:
                active[a_acc > 0.99] = False
                if not np.any(active):
                    break

            active_idx = np.where(active)[0]

            # world → voxel
            voxels = positions[active_idx] * inv_spacing[np.newaxis, :]

            # Bounds check
            in_bounds = np.all((voxels >= 0) & (voxels < shape_arr), axis=1)

            if np.any(in_bounds):
                valid_voxels = voxels[in_bounds]
                intensities = map_coordinates(
                    self.pet_volume,
                    valid_voxels.T,
                    order=1,
                    mode='nearest',
                )

                # TF lookup
                lut_idx = np.clip((intensities * 255).astype(np.int32), 0, 255)
                alpha = self.opacity_lut[lut_idx]   # (K,)
                color = self.color_lut[lut_idx]      # (K, 3)

                global_idx = active_idx[in_bounds]

                # Front-to-back compositing
                one_minus_a = 1.0 - a_acc[global_idx]
                contrib = one_minus_a * alpha

                r_acc[global_idx] += contrib * color[:, 0]
                g_acc[global_idx] += contrib * color[:, 1]
                b_acc[global_idx] += contrib * color[:, 2]
                a_acc[global_idx] += contrib

            # Advance positions toward SOI
            positions[active_idx] += step_vec[np.newaxis, :]

        pet_rgba = np.stack([r_acc, g_acc, b_acc, a_acc], axis=-1)
        pet_rgba = pet_rgba.reshape(H, W, 4)
        return np.clip(pet_rgba, 0, 1)
