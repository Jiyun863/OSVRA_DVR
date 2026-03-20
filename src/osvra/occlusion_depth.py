"""
Phase 2: Occlusion Distance Map 생성
SOI에서 viewpoint 방향으로 CT ray marching, opacity limit에 도달하는 거리(mm) 기록
"""

import numpy as np
from scipy.ndimage import map_coordinates
from src.osvra.volume_bridge import VolumeBridge


class OcclusionDepthComputer:
    """SOI에서 viewpoint 방향 CT ray marching으로 occlusion distance map 생성"""

    def __init__(
        self,
        ct_volume: np.ndarray,
        ct_spacing: tuple,
        ct_tf_nodes: list,
        opacity_limit: float = 0.95,
        sample_step_mm: float = 1.0,
        max_distance_mm: float = 500.0,
    ):
        """
        Args:
            ct_volume: (X, Y, Z) normalized [0, 1]
            ct_spacing: (sx, sy, sz) mm
            ct_tf_nodes: [[pos, r, g, b, alpha], ...]
            opacity_limit: CT DVR opacity limit (0~1)
            sample_step_mm: ray marching step size in mm
            max_distance_mm: maximum ray distance in mm
        """
        self.ct_volume = ct_volume
        self.ct_spacing = np.array(ct_spacing, dtype=np.float64)
        self.opacity_lut, _ = VolumeBridge.build_tf_luts(ct_tf_nodes)
        self.opacity_limit = opacity_limit
        self.sample_step = sample_step_mm
        self.max_distance = max_distance_mm

    def compute(
        self,
        soi_plane,
        view_direction: np.ndarray,
    ) -> tuple:
        """Occlusion distance map 계산

        Args:
            soi_plane: SOIPlane instance
            view_direction: (3,) normalized camera->focal direction

        Returns:
            depth_map: (H, W) Euclidean distance in mm, NaN if no hit
            valid_mask: (H, W) bool, True if opacity limit reached
        """
        H, W = soi_plane.resolution
        ray_starts = soi_plane.get_ray_start_points()  # (H, W, 3)

        # ray direction: SOI -> viewpoint (= -view_direction)
        ray_dir = -np.asarray(view_direction, dtype=np.float64)
        ray_dir = ray_dir / np.linalg.norm(ray_dir)

        step_vec = ray_dir * self.sample_step  # (3,)
        max_steps = int(self.max_distance / self.sample_step)

        depth_map = np.full((H, W), np.nan, dtype=np.float32)
        valid_mask = np.zeros((H, W), dtype=bool)

        shape = self.ct_volume.shape

        # Vectorized ray marching: process all rays simultaneously
        # Reshape ray_starts to (N, 3) for batch processing
        N = H * W
        positions = ray_starts.reshape(N, 3).copy()  # (N, 3)
        accumulated_opacity = np.zeros(N, dtype=np.float64)
        done = np.zeros(N, dtype=bool)
        result_depth = np.full(N, np.nan, dtype=np.float32)

        for step in range(max_steps):
            if np.all(done):
                break

            active = ~done

            # world -> voxel
            voxels = positions[active] / self.ct_spacing[np.newaxis, :]

            # bounds check (vectorized)
            shape_arr = np.array(shape, dtype=np.float64) - 1
            in_bounds = np.all((voxels >= 0) & (voxels < shape_arr), axis=1)

            # 볼륨 밖으로 나간 ray는 다시 들어올 수 없으므로 종료
            active_indices = np.where(active)[0]
            out_of_bounds = ~in_bounds
            if np.any(out_of_bounds):
                oob_global = active_indices[out_of_bounds]
                done[oob_global] = True

            # for those in bounds, sample intensity
            if np.any(in_bounds):
                valid_voxels = voxels[in_bounds]
                intensities = map_coordinates(
                    self.ct_volume,
                    valid_voxels.T,
                    order=1,
                    mode='nearest',
                )

                # TF lookup
                lut_indices = np.clip((intensities * 255).astype(int), 0, 255)
                alphas = self.opacity_lut[lut_indices]

                in_bounds_global = active_indices[in_bounds]

                # front-to-back opacity accumulation
                prev_opacity = accumulated_opacity[in_bounds_global]
                accumulated_opacity[in_bounds_global] += (1.0 - prev_opacity) * alphas

                # Check which rays hit the limit
                hit_limit = accumulated_opacity[in_bounds_global] >= self.opacity_limit
                if np.any(hit_limit):
                    hit_global = in_bounds_global[hit_limit]
                    result_depth[hit_global] = step * self.sample_step
                    done[hit_global] = True

            # advance all active positions
            positions[active] += step_vec[np.newaxis, :]

        depth_map = result_depth.reshape(H, W)
        valid_mask = ~np.isnan(depth_map)

        return depth_map, valid_mask
