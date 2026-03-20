import sys
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["JOBLIB_START_METHOD"] = "forkserver" # 선택사항

# 기존 VTK 설정
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['MESA_GL_VERSION_OVERRIDE'] = '3.2'
os.environ['VTK_USE_OSMESA'] = '1'

def main():
    clear_python_cache()
    
    # ⭐ 추가: UI가 뜨기 전 모델 파일 확인 및 다운로드
    # check_and_download_model()
    
    """메인 함수"""
    os.environ['TORCH_CUDA_ARCH_LIST'] = '8.6'
    # PyQt6 애플리케이션 생성
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette, QColor
    
    app = QApplication(sys.argv)
    
    # 스타일 설정
    app.setStyle('Fusion')
    
    # 다크 테마 적용
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    # ⭐ 메인 윈도우 생성 - 절대 import 경로 사용
    from src.main_window import VolumeRenderingMainWindow
    
    window = VolumeRenderingMainWindow()
    window.show()
    
    # 이벤트 루프 실행
    return app.exec()

def clear_python_cache():
    """Python 캐시 파일들 정리"""
    import shutil
    import glob
    
    try:
        cache_dirs = []
        for root, dirs, files in os.walk('.'):
            for dir_name in dirs:
                if dir_name == '__pycache__':
                    cache_path = os.path.join(root, dir_name)
                    cache_dirs.append(cache_path)
        
        for cache_dir in cache_dirs:
            try:
                shutil.rmtree(cache_dir)
            except Exception as e:
                pass
        
        pyc_files = glob.glob('**/*.pyc', recursive=True)
        for pyc_file in pyc_files:
            try:
                os.remove(pyc_file)
            except Exception as e:
                pass
        
    except Exception as e:
        print(f"❌ 캐시 정리 중 오류: {e}")

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)