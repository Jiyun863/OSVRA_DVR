"""
NPY 파일 로더
"""
import numpy as np
from typing import Tuple, Optional
from .base_loader import BaseVolumeLoader


class NpyLoader(BaseVolumeLoader):
    """NumPy (.npy) 파일 로더"""
    
    def load(self, file_path: str) -> Tuple[np.ndarray, Optional[Tuple]]:
        volume_data = np.load(file_path)
        voxel_spacing = (1.0, 1.0, 1.0)  # 기본값
        return volume_data, voxel_spacing
    
    def get_supported_extensions(self) -> list:
        return ['.npy']