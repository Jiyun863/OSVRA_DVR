"""
볼륨 로더 추상 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import Tuple, Optional
import numpy as np


class BaseVolumeLoader(ABC):
    """볼륨 로더의 추상 베이스 클래스"""
    
    @abstractmethod
    def load(self, file_path: str) -> Tuple[np.ndarray, Optional[Tuple[float, float, float]]]:
        """
        볼륨 데이터를 로드합니다.
        
        Returns:
            Tuple[volume_data, voxel_spacing]
            - volume_data: np.ndarray (W, H, D)
            - voxel_spacing: (x, y, z) 또는 None
        """
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> list:
        """지원하는 파일 확장자 목록 반환"""
        pass