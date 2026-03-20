"""
Raw 파일 로더
file_panel.py에서 분리됨
"""
import numpy as np
from typing import Tuple, Optional
from .base_loader import BaseVolumeLoader


class RawLoader(BaseVolumeLoader):
    """Raw (.raw, .dat) 파일 로더"""
    
    def __init__(self):
        self.params = None  # RawDataDialog에서 받은 파라미터
    
    def set_params(self, shape, dtype_str, endian, voxel_spacing):
        """Raw 파일 로딩에 필요한 파라미터 설정"""
        self.params = {
            'shape': shape,
            'dtype_str': dtype_str,
            'endian': endian,
            'voxel_spacing': voxel_spacing
        }
    
    def load(self, file_path: str) -> Tuple[np.ndarray, Optional[Tuple]]:
        """raw 데이터 직접 로드"""
        
        # ⭐ params 체크
        if self.params is None:
            raise ValueError("Raw 파일 로딩 전에 set_params()를 호출해야 합니다.")
        
        # ⭐ params에서 값 꺼내기
        shape = self.params['shape']
        dtype_str = self.params['dtype_str']
        endian = self.params['endian']
        voxel_spacing = self.params['voxel_spacing']
        
        # 데이터 타입 매핑
        dtype_map = {
            'uint8': np.uint8, 'int8': np.int8,
            'uint16': np.uint16, 'int16': np.int16, 
            'uint32': np.uint32, 'int32': np.int32,
            'float32': np.float32, 'float64': np.float64
        }
        
        # 바이트 순서 설정
        endian_map = {
            'little': '<',
            'big': '>'
        }
        
        endian_char = endian_map.get(endian, '<')
        dtype = np.dtype(dtype_map[dtype_str])
        dtype_with_endian = dtype.newbyteorder(endian_char)
        
        # ⭐ file_path 사용 (raw_file_path 아님)
        print(f"Reading raw data from: {file_path}")
        raw_data = np.fromfile(file_path, dtype=dtype_with_endian)
        
        # 데이터 크기 확인
        expected_size = np.prod(shape)
        if len(raw_data) != expected_size:
            print(f"경고: 데이터 크기 불일치. 예상: {expected_size}, 실제: {len(raw_data)}")
            if len(raw_data) < expected_size:
                raise ValueError("데이터가 부족합니다. 차원을 확인하세요.")
            else:
                print("데이터를 예상 크기로 자릅니다.")
                raw_data = raw_data[:expected_size]
        
        # 데이터 형태 변환 (Fortran order)
        print(f"Reshaping data to: {shape}")
        reshaped_data = raw_data.reshape(shape, order='F')
        
        # 볼륨 데이터로 설정
        volume_data = reshaped_data.astype(np.float32)
        
        print(f"📊 Raw 데이터 로드 완료: {volume_data.shape}")
        
        # ⭐ Tuple 반환 (volume_data, voxel_spacing)
        return volume_data, voxel_spacing

    def get_supported_extensions(self) -> list:
        return ['.raw', '.dat']