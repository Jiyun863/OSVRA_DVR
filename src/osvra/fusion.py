"""
Phase 6: PET SOI + CT Augmentation Fusion
PET RGBA와 CT augmentation의 pixel-level fusion
"""

import numpy as np


class FusionRenderer:
    """PET RGBA와 CT augmentation의 pixel-level fusion"""

    @staticmethod
    def fuse(
        pet_rgba: np.ndarray,
        ct_aug_rgba: np.ndarray,
        fusion_ratio: float = 0.5,
    ) -> np.ndarray:
        """PET RGBA와 CT augmentation 합성

        Args:
            pet_rgba: (H, W, 4) RGBA float [0, 1] — TF가 적용된 PET
            ct_aug_rgba: (H, W, 4) RGBA float [0, 1] CT augmentation
            fusion_ratio: PET 비율 (0.0=CT only, 1.0=PET only)

        Returns:
            fused_rgba: (H, W, 4) RGBA float [0, 1]
        """
        # Ensure ct_aug_rgba matches dimensions
        if ct_aug_rgba.shape[:2] != pet_rgba.shape[:2]:
            from scipy.ndimage import zoom
            zoom_factors = (
                pet_rgba.shape[0] / ct_aug_rgba.shape[0],
                pet_rgba.shape[1] / ct_aug_rgba.shape[1],
                1.0,
            )
            ct_aug_rgba = zoom(ct_aug_rgba, zoom_factors, order=1)

        # Pixel-level fusion: weighted blend
        fused = fusion_ratio * pet_rgba + (1.0 - fusion_ratio) * ct_aug_rgba
        return np.clip(fused, 0, 1).astype(np.float32)

    @staticmethod
    def fuse_alpha_blend(
        pet_rgba: np.ndarray,
        ct_aug_rgba: np.ndarray,
    ) -> np.ndarray:
        """Alpha-based fusion: PET을 CT augmentation 위에 오버레이

        Args:
            pet_rgba: (H, W, 4) RGBA float [0, 1]
            ct_aug_rgba: (H, W, 4) RGBA float [0, 1]

        Returns:
            fused_rgba: (H, W, 4) RGBA float [0, 1]
        """
        pet_alpha = pet_rgba[:, :, 3:4]

        # Over compositing: PET over CT
        fused_rgb = pet_rgba[:, :, :3] * pet_alpha + ct_aug_rgba[:, :, :3] * (1.0 - pet_alpha)
        fused_a = pet_alpha + ct_aug_rgba[:, :, 3:4] * (1.0 - pet_alpha)

        fused = np.concatenate([fused_rgb, fused_a], axis=2)
        return np.clip(fused, 0, 1).astype(np.float32)
