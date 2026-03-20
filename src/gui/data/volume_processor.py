"""
볼륨 데이터 전처리 모듈
file_panel.py에서 분리됨
"""
import numpy as np

class VolumeProcessor:
    """볼륨 데이터 전처리 클래스"""

    @staticmethod
    def process(volume_data: np.ndarray) -> np.ndarray:
            """볼륨 데이터 전처리"""
            try:
                # NumPy 배열로 변환 (Fortran order 유지)
                volume_data = np.array(volume_data, dtype=np.float32, order='F')
                
                print(f"   Volume Shape: {volume_data.shape}")
                print(f"   Volume Dtype: {volume_data.dtype}")
                print(f"   Volume Dimension: {volume_data.ndim}")
                
                # 1차원 데이터 처리
                if volume_data.ndim == 1:
                    print("⚠️ 1차원 데이터 감지 - 3차원으로 reshape 필요")
                    cube_size = int(np.round(len(volume_data) ** (1/3)))
                    if cube_size ** 3 == len(volume_data):
                        volume_data = volume_data.reshape(cube_size, cube_size, cube_size, order='F')
                        print(f"   큐브 형태로 reshape: {volume_data.shape}")
                    else:
                        raise ValueError(f"1차원 데이터를 3차원으로 변환할 수 없습니다. 길이: {len(volume_data)}")
                
                # 2차원 데이터 처리
                elif volume_data.ndim == 2:
                    print("⚠️ 2차원 데이터 감지 - 3차원으로 확장")
                    volume_data = volume_data[np.newaxis, :, :]
                    volume_data = np.asfortranarray(volume_data)
                    print(f"   3차원으로 확장: {volume_data.shape}")
                
                # 4차원 이상 데이터 처리
                elif volume_data.ndim > 3:
                    print(f"⚠️ {volume_data.ndim}차원 데이터 감지 - 첫 3차원만 사용")
                    volume_data = volume_data[:, :, :, 0] if volume_data.ndim == 4 else volume_data
                    while volume_data.ndim > 3:
                        volume_data = volume_data[..., 0]
                    volume_data = np.asfortranarray(volume_data)
                    print(f"   3차원으로 축소: {volume_data.shape}")
                
                # 3차원인 경우 Fortran order 확인
                elif volume_data.ndim == 3:
                    if not volume_data.flags['F_CONTIGUOUS']:
                        print("⚠️ C order 데이터 - Fortran order로 변환")
                        volume_data = np.asfortranarray(volume_data)
                
                # 최소 크기 검증
                if any(dim < 2 for dim in volume_data.shape):
                    raise ValueError(f"볼륨 차원이 너무 작습니다: {volume_data.shape}")
                
                # NaN 및 무한값 처리
                if np.any(np.isnan(volume_data)) or np.any(np.isinf(volume_data)):
                    print("⚠️ NaN 또는 무한값 발견 - 0으로 대체")
                    volume_data = np.nan_to_num(volume_data, nan=0.0, posinf=1.0, neginf=0.0)
                
                # 정규화 (0-1 범위)
                if volume_data.max() > volume_data.min():
                    volume_data = ((volume_data - volume_data.min()) / 
                                (volume_data.max() - volume_data.min()))
                    print(f"   정규화 완료: {volume_data.min():.3f} ~ {volume_data.max():.3f}")
                else:
                    print("⚠️ 모든 값이 동일 - 정규화 스킵")
                
                # 최종 Fortran order 확인
                volume_data = np.asfortranarray(volume_data)
                return volume_data
                
            except Exception as e:
                print(f"❌ 볼륨 데이터 처리 오류: {e}")
                return None