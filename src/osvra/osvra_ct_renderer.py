"""
Phase 5: Weighted CT Augmentation Rendering
Vectorized back-to-front compositing with logistic weight
"""

import numpy as np
from scipy.ndimage import map_coordinates
from src.osvra.volume_bridge import VolumeBridge


class OSVRACTRenderer:
    """Logistic-weighted CT augmentation ray marching (vectorized)"""

    def __init__(
        self,
        ct_volume: np.ndarray,
        ct_spacing: tuple,
        ct_tf_nodes: list,
        sample_step_mm: float = 1.0,
        max_distance_mm: float = 500.0,
    ):
        """
        Args:
            ct_volume: (X, Y, Z) normalized [0, 1]
            ct_spacing: (sx, sy, sz) mm
            ct_tf_nodes: [[pos, r, g, b, alpha], ...]
            sample_step_mm: ray marching step size in mm
            max_distance_mm: maximum ray distance in mm
        """
        self.ct_volume = ct_volume
        self.ct_spacing = np.array(ct_spacing, dtype=np.float64)
        self.opacity_lut, self.color_lut = VolumeBridge.build_tf_luts(ct_tf_nodes)
        self.sample_step = sample_step_mm
        self.max_distance = max_distance_mm

    def render(
        self,
        soi_plane,
        view_direction: np.ndarray,
        weight_func,
    ) -> np.ndarray:
        """Vectorized back-to-front CT augmentation rendering

        All N=H*W rays are processed simultaneously per step.

        Args:
            soi_plane: SOIPlane instance
            view_direction: (3,) normalized camera->focal direction
            weight_func: LogisticWeightFunction instance

        Returns:
            ct_aug_rgba: (H, W, 4) RGBA float [0, 1]
        """
        H, W = soi_plane.resolution
        N = H * W
        ray_starts = soi_plane.get_ray_start_points()  # (H, W, 3)

        # Ray direction: SOI → viewpoint (back-to-front: SOI(back) → camera(front))
        ray_dir = -np.asarray(view_direction, dtype=np.float64)
        ray_dir = ray_dir / np.linalg.norm(ray_dir)
        step_vec = ray_dir * self.sample_step  # (3,)
        max_steps = int(self.max_distance / self.sample_step)

        shape = self.ct_volume.shape
        shape_arr = np.array(shape, dtype=np.float64) - 1
        inv_spacing = 1.0 / self.ct_spacing  # for world→voxel

        # Pre-compute weight LUT
        distances = np.arange(max_steps, dtype=np.float64) * self.sample_step
        weight_lut = weight_func(distances).astype(np.float32)  # (max_steps,)

        # Flatten rays
        positions = ray_starts.reshape(N, 3).copy()  # (N, 3)

        # Accumulators (back-to-front)
        r_acc = np.zeros(N, dtype=np.float32)
        g_acc = np.zeros(N, dtype=np.float32)
        b_acc = np.zeros(N, dtype=np.float32)
        a_acc = np.zeros(N, dtype=np.float32)

        active = np.ones(N, dtype=bool)  # rays still marching

        for step in range(max_steps):
            if not np.any(active):
                break

            active_idx = np.where(active)[0]

            # world → voxel
            voxels = positions[active_idx] * inv_spacing[np.newaxis, :]

            # Vectorized bounds check
            in_bounds = np.all((voxels >= 0) & (voxels < shape_arr), axis=1)

            # 볼륨 밖으로 나간 ray는 다시 들어올 수 없으므로 종료
            out_of_bounds = ~in_bounds
            if np.any(out_of_bounds):
                oob_global = active_idx[out_of_bounds]
                active[oob_global] = False

            if np.any(in_bounds):
                valid_voxels = voxels[in_bounds]
                intensities = map_coordinates(
                    self.ct_volume,
                    valid_voxels.T,
                    order=1,
                    mode='nearest',
                )

                # TF lookup
                lut_idx = np.clip((intensities * 255).astype(np.int32), 0, 255)
                alpha = self.opacity_lut[lut_idx]   # (K,)
                color = self.color_lut[lut_idx]      # (K, 3)

                # Apply logistic weight
                w = weight_lut[step]
                weighted_alpha = alpha * w  # (K,)

                # Global indices for in-bounds active rays
                global_idx = active_idx[in_bounds]

                # Back-to-front compositing:
                # C_out = C_s * a_s + C_in * (1 - a_s)
                # a_out = a_s + a_in * (1 - a_s)
                one_minus_wa = 1.0 - weighted_alpha

                r_acc[global_idx] = color[:, 0] * weighted_alpha + r_acc[global_idx] * one_minus_wa
                g_acc[global_idx] = color[:, 1] * weighted_alpha + g_acc[global_idx] * one_minus_wa
                b_acc[global_idx] = color[:, 2] * weighted_alpha + b_acc[global_idx] * one_minus_wa
                a_acc[global_idx] = weighted_alpha + a_acc[global_idx] * one_minus_wa

            # Advance active positions
            positions[active_idx] += step_vec[np.newaxis, :]

        # Reshape to image
        ct_aug = np.stack([r_acc, g_acc, b_acc, a_acc], axis=-1)
        ct_aug = ct_aug.reshape(H, W, 4)
        return np.clip(ct_aug, 0, 1)
