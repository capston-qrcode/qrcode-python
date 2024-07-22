def gf_mult_noLUT(x, y, prim=0b1011, field_charac_full=1 << 3):
    """
    GF(2^m)에서 곱셈을 수행합니다.
    prim: 원시 다항식
    field_charac_full: 유한체의 크기 (2^m)
    """
    r = 0
    while y:
        if y & 1:
            r ^= x
        x <<= 1
        if x & field_charac_full:
            x ^= prim
        y >>= 1
    return r

# 원시 다항식 및 유한체의 크기 정의
prim = 0b1011  # x^3 + x + 1
field_charac_full = 1 << 3  # 2^3

# α를 정의 (여기서는 0b10로 설정, 이는 2를 의미)
alpha = 0b10

# 갈루아 필드의 원소를 저장할 리스트
gf_elements = [0] * field_charac_full

# α의 거듭제곱을 계산하여 필드의 원소를 생성
for i in range(field_charac_full):
    gf_elements[i] = alpha
    alpha = gf_mult_noLUT(alpha, 0b10, prim, field_charac_full)
    if alpha >= field_charac_full:
        alpha ^= prim

# 결과 출력
for i, elem in enumerate(gf_elements):
    print(f"α^{i} = {elem}")  # 이진수로 출력