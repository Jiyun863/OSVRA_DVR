"""
통합 볼륨 로더 - Strategy Pattern
"""
from typing import Tuple, Optional
import numpy as np

from .nifti_loader import NIfTILoader
from .raw_loader import RawLoader
from .npy_loader import NpyLoader
from .mata_loader import MetaImageLoader
from .volume_processor import VolumeProcessor


class VolumeLoader:
    """통합 볼륨 로더 - 확장자에 따라 적절한 로더 선택"""
    
    def __init__(self):
        self.loaders = {
            '.nii': NIfTILoader(),
            '.nii.gz': NIfTILoader(),
            '.npy': NpyLoader(),
            '.raw': RawLoader(),
            '.dat': RawLoader(),
            '.mha': MetaImageLoader(),
            '.mhd': MetaImageLoader(),
        }
        self.processor = VolumeProcessor()
    
    def load(self, file_path: str, raw_params: dict = None) -> Tuple[np.ndarray, Tuple]:
        ext = self._get_extension(file_path)
        
        if ext not in self.loaders:
            raise ValueError(f"지원하지 않는 파일 형식: {ext}")
        
        loader = self.loaders[ext]
        
        # ⭐ Raw 파일인 경우 파라미터 설정
        if ext in ['.raw', '.dat']:
            if raw_params is None:
                raise ValueError("Raw 파일 로딩에는 파라미터가 필요합니다.")
            loader.set_params(
                shape=raw_params['shape'],
                dtype_str=raw_params['dtype_str'],      # ⚠️ 'dtype' 키 확인
                endian=raw_params['endian'],
                voxel_spacing=raw_params['voxel_spacing']
            )
        
        # 로드 및 전처리
        volume_data, voxel_spacing = loader.load(file_path)
        processed_volume = self.processor.process(volume_data)
        
        return processed_volume, voxel_spacing
    
    def _get_extension(self, file_path: str) -> str:
        """파일 확장자 추출 (.nii.gz 처리 포함)"""
        if file_path.endswith('.nii.gz'):
            return '.nii.gz'
        return '.' + file_path.split('.')[-1].lower()