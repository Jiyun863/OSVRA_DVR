<aside>
PET-CT

- 보통 암의 전이 여부 또는 암을 검출하기 위해 사용한다
- FDG 라는 포도당과 유사한 방사성 의약품을 주사한 뒤에 PET-CT를 통해 촬영한다
- PET은 포도당의 흡수 여부를 시각적으로 판단하여 암세포는 포도당 흡수를 기하급수적으로 많이 하기 때문에 암인 경우에 많이 검출되는 것을 확인가능하다
</aside>

# Abstract

- 목적 : PET-CT 영상 시각화 시 발생하는 Occlusion 문제를 해결하겠다
- PET-CT 는 PET의 병리/생리학적 정보와 CT의 해부학적 정보를 그린다
    - PET는 2d slice of interest (SOI)를 획득하고
    - CT는 DVR로 렌더링한다
    - Volume Rendering으로 PET-CT를 합칠 수 있다
- 근데, DVR은 전체 볼륨을 그리기 때문에 SOI에서 tumor 같은 ROI를 가릴 수 있다
    - volume clipping을 사용하는 방법도 있지만 적절한 depth 찾는데에 너무 오래걸림
- TF는 ROI를 시각화 할 수 있다
    - parameter tuning이 복잡하고
    - region을 정의하는 데이터 전처리가 필요하다 (여기서 전처리는 segmentation 같음)
- 이 논문의 제안 : CT의 DVR에서 PET가 volume contextual information에 의해 증강되는 기법
    - SOI에서 CT 때문에 거슬렸던 부분이 최소화된다
    - SOI 앞에 CT 복셀로 얻어진 가림 정보를 고려해서 깊이 파라미터를 자동으로 계산한다
    - 깊이 파라미터는 DVR로부터 보여질 문맥적 정보의 양을 조절하는 opacity weight function을 생성한다

# Introduction

- PET-CT는 보통 cross-sctional view로만 본다
    
- DVR을 활용하면 전체 볼륨을 렌더링할 수 있기 때문에 둘러싸인 형태와의 관계를 더 쉽게 고려 가능
    - DVR의 occlusion 문제, 관행, 적절한 소프트웨어 부재로 DVR은 잘 사용하지 않고 있다
    - 이 문제는 다중 모달리티로 가면 더 악화된다
        
        - (a) 그림처럼, 시점 기준으로 거리 순서로 렌더링되기 때문에 ROI가 가려지게 된다
        - 이에 대한 대안이 2d PET slice(SOI)에 3D CT volume을 증강하는 방식(slice-based volume rendering)
            - (b)처럼 PET의 병리/생리학적 정보와 CT의 구조적인 정보를 모두 볼 수 있다
            - 근데 (b)도 여전히 ROI가 CT skull 때문에 가려진다
        - 사실 이런 occlusion을 막을 방법은 TF를 조절하는 것이다
            - 하지만 TF는 전체 볼륨에 적용되기 때문에 특정 개별 구조에 적용할 수가 없다
                - 이에 대안 대안이 maximum intensity difference accumulation 과 depth-based feature enhancement가 있다
                - 이런 ray-casting 기반 DVR 접근은 여전히 전체 볼륨에 적용되기 때문에 ROI가 잘 보이게 유지된다고 볼 수 없다
        - 이에 대한 대안으로 volume clipping도 있다
            - 적절한 depth를 찾는데 너무 오랜 시간이 걸린다
            - 가치있는 문맥적 단서를 없애는 결과가 나타날 수도 있다
            - (내생각) 구조적인 3d 정보가 다 날라가는거 아님? (DVR 쓰는 의미 없어진다고 봄)
        - 여기에서의 제안: augmentation depth parameter를 자동으로 계산하기 위해 PET 앞에 CT 복셀들로부터 계산된 occlusion 정보를 사용한다
            - **Occlusion and Slice-based Volume Rendering Augmentation(OSVRA) 제안**
            - “어디에서 자를 것인가가 핵심”
                - PET 단면을 가리는 CT 구조물이 무엇인지 파악하고, 그 직전까지만 렌더링을 허용하는 것
                - 깊이 계산과정에서 개별 복셀 단위가 아니라 같은 CT 구조에 속한 복셀들을 그룹화해서 구조 단위로 분석한다
                - CT DVR에의해 생성되는 증강의 정도(amount)를 depth parameter로 제어한다
                    - 이를 통해, SOI의 시야를 가리지 않으면서도 SOI 인접한 관련 구조들의 3차원 맥락 정보를 보존한다
        - **나의 궁금증 : Volume Clipping 해서 쓰는 거랑 다른게 뭐임??????**
        - Depth parameter를 추정하는 알고리즘은 있고 여기에서 성능과 시각적 품질을 고도화하기 위해 세 가지 핵심 요소를 추가한거래
            - Histogram Analysis
            - Context Preserving Weight Function(깊이 계산 과정에 해당 함수 통합)
            - Flexible Application of Varying Transfer Functions(시각적 품질 개선)

# Approach

- 6단계로 진행된다
    1. 유저가 SOI 선택
    2. volume ray-casting에서 opacity accumulation 컨셉을 사용해서, **slice에서 각 sample의 occlusion distance를 계산**한다.[그림 3에 (b) 빨간색 화살표], 이 거리는 각 샘플과 관련된 CT 정보가 해당 샘플의 가시성을 저해하지 않으면서 최대한으로 보여질 수 있는 지점까지의 거리. 여기서 CT 볼륨은 하나의 정육면체로 표현됨
        1. 그니까 이게 PET에서 ray를 쏴가지고 transmittance가 0이 될 때까지의 거리를 구하겠다 그런 것 같은데?
    3. **PET 및 CT 볼륨을 위해 사전에 정의된 TF가 사용**된다(PET: 생리학적, CT: 해부학적)
        1. 그림(C)는 슬라이스 내 모든 샘플의 occlusion distance를 나타내는 맵을 구축함
    4. [그림3(d)] occlusion distance map을 바탕으로 히스토그램을 생성하는 과정, augmentation depth parameter를 계산하는데 사용됨. 이 파라미터는 슬라이스에 대한 occlusion을 피하면서 렌더링될 CT의 DVR 양을 조절함(default로는 히스토그램의 첫번째 피크가 사용됨)
    5. 계산된 augmentation depth parameter 값을 변곡점으로 사용하여 로지스틱 함수 형태의 불투명도 가중치 곡선(opacity weight curve)를 생성
        1. CT TF와 함께 사용, D 기준으로 이전은 강조 이후는 약화시키는 방식
        2. 그 다음 CT 볼륨은 CT TF와 도출된 불투명도 가중치 곡선을 적용하여 렌더링 됨
        3. 최종적으로 PET 슬라이스 위에 융합됨.
    6. 융합할 때는 비율을 지정해서 유합할 수 있음 (50:50, 70:30 등등)

### Occlusion Distance Histogram Generation and Augmentation Depth Computation

- depth parameter를 계산하기 위해서 back-to-front ray casting을 사용함
    - SOI가 view point로 ray를 쏜다
    - CT 복셀의 누적 불투명도가 기록된다
    - 누적 불투명도가 1이 되면 ray가 끝난다
    - ray의 거리를 유클리드 거리로 계산한다
    - 동일한 구조에 속하는 복셀들은 TF에서 동일한 intensity에 있을 거고 이는 동일한 opacity 와 color가 매핑되어 있으니까 비슷한 구조는 비슷한 occlusion distance(ray 길이)를 가질 것이다
        - 이를 통해, 구조 단위 분석을 위한 복셀 그룹화가 가능하다
            
    - 거리 기반 히스토그램에 대해서 첫 번째 피크를 선택하면 ray의 가장 짧은 거리에서 가림이 발생하는 구조까지 렌더링 하겠다는 뜻이고 그러면 더 긴 ray에서 끝나는 구조들은 도중에 렌더링이 끊겨서 일부만 렌더링 된다

### Dynamic Generation of Opacity Weight Curve

- 구한 D에 대해서 이 D를 변곡점으로 하는 y축으로 반전된 logistic function을 사용함
    - 이걸 사용하게 되면 SOI 주변 복셀들은 가중치가 높고
    - D 주변은 원래 복셀 만큼 가져가게 되고
        
    - 멀어지면 확 그 기여도가 떨어진다
        
        - 이게 그 logistic function의 수식이고
        - d_i는 i번째 복셀의 거리
        - B는 몰라도 되고
        - A는 minimum weight value
        - C는 maximum weight value
            - 경험적으로 A = 0.0001, C = 1.0 이 좋더라

### Fusion of SOI of PET and DVR of CT

- 그냥 back-to-front 하는 공식에다가 weight를 추가한다

# Implementation

### Occlusion Distance Map Generation

- distance map을 구하기 위해서 SOI plane을 back face로 두고 카메라로 back-to-front ray-casting 진행
- (1)번 수식에 따라서 불투명도가 1이 되면 early stopping을 진행하고 해당 distance를 모은 뒤에 histogram 생성에 활용
- 이를 통해서 D를 구함