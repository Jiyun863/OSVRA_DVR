import numpy as np
from scipy.optimize import minimize
from src.core.cost_function import VisibilityCostFunction

class TFOptimizer:
    def __init__(self, analyzer_data, current_tf_nodes):
        """
        Args:
            analyzer_data: FeatureAnalyzer 결과
            current_tf_nodes: 현재 적용 중인 TF 노드 리스트 (초기 상태)
        """
        self.data = analyzer_data
        self.initial_nodes = current_tf_nodes
        
        # 초기 Nodes를 256 LUT 배열로 변환
        self.base_lut = self._nodes_to_lut(current_tf_nodes)
        
        # 비용 함수 초기화 (Base LUT 전달)
        self.cost_function = VisibilityCostFunction(analyzer_data, self.base_lut)

    def optimize(self, ftol=1e-3, maxiter=30):
        print("🚀 Relative Optimization Started...")
        
        # 파라미터 정의: [Boost Amplitude, Boost Width, Global Damping]
        # x[0] (Boost): 0.0(변화없음) ~ 1.0(강한 강조)
        # x[1] (Width): 5.0 ~ 30.0
        # x[2] (Damp): 0.0(다 지움) ~ 1.0(그대로 유지)
        
        # 초기값: 약간 강조하고, 배경은 살짝 어둡게(0.8) 시작
        x0 = [0.3, 15.0, 0.8]
        bounds = [(0.0, 1.0), (5.0, 50.0), (0.1, 1.0)]
        
        res = minimize(
            self.cost_function, 
            x0, 
            method='L-BFGS-B', 
            bounds=bounds,
            options={'ftol': ftol, 'maxiter': maxiter}
        )
        
        if res.success:
            print(f"✅ Optimized Delta: Boost={res.x[0]:.2f}, Damp={res.x[2]:.2f}")
            return self._apply_result_to_nodes(res.x)
        else:
            print("⚠️ Converge failed, applying best effort.")
            return self._apply_result_to_nodes(res.x)

    def _nodes_to_lut(self, nodes):
        """TF Nodes -> 256 Opacity Array 변환"""
        lut = np.zeros(256)
        sorted_nodes = sorted(nodes, key=lambda x: x[0])
        
        for i in range(256):
            t = i / 255.0
            if t <= sorted_nodes[0][0]: val = sorted_nodes[0][4]
            elif t >= sorted_nodes[-1][0]: val = sorted_nodes[-1][4]
            else:
                for j in range(len(sorted_nodes)-1):
                    if sorted_nodes[j][0] <= t <= sorted_nodes[j+1][0]:
                        r = (t - sorted_nodes[j][0]) / (sorted_nodes[j+1][0] - sorted_nodes[j][0])
                        val = sorted_nodes[j][4]*(1-r) + sorted_nodes[j+1][4]*r
                        break
            lut[i] = val
        return lut

    def _apply_result_to_nodes(self, params):
        """
        최적화된 파라미터(LUT 변형)를 다시 GUI용 Node 리스트로 변환.
        기존 노드를 유지하되, 타겟 구간에 '가우시안 노드'를 추가하고, 
        기존 노드들의 Opacity를 Damping하는 방식.
        """
        boost_amp, boost_width, damp_factor = params
        target_range = self.data['target_range']
        mu = (target_range[0] + target_range[1]) / 2.0
        
        new_nodes = []
        
        # 1. 기존 노드 Damping (배경 억제)
        for node in self.initial_nodes:
            # node: [pos, r, g, b, alpha]
            # alpha 값에 damp_factor 곱하기
            new_node = list(node)
            new_node[4] *= damp_factor 
            new_nodes.append(new_node)
            
        # 2. 타겟 부스팅 노드 추가 (Additive Effect)
        # 단순히 노드를 추가하면 선형 보간으로 인해 모양이 망가질 수 있으므로,
        # 타겟 중심부에 새로운 노드를 삽입합니다.
        
        # Boost Peak Node (Reddish Color for Saliency)
        # 위치: mu, Opacity: boost_amp (기존 값에 더해지는 효과를 위해 높게 설정)
        peak_node = [mu/255.0, 1.0, 0.2, 0.2, min(1.0, boost_amp + 0.2)] 
        
        # 범위를 잡아주는 앵커 노드들
        left_node = [max(0, (mu - boost_width)/255.0), 1.0, 0.2, 0.2, 0.0]
        right_node = [min(1.0, (mu + boost_width)/255.0), 1.0, 0.2, 0.2, 0.0]
        
        new_nodes.append(left_node)
        new_nodes.append(peak_node)
        new_nodes.append(right_node)
        
        # 위치 기준 정렬
        return sorted(new_nodes, key=lambda x: x[0])