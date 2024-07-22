def init_galois_field():
    exp = [0] * 512  # 지수 테이블
    log = [0] * 256  # 로그 테이블

    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11d  # 다항식 x^8 + x^4 + x^3 + x^2 + 1
    for i in range(255, 512):
        exp[i] = exp[i - 255]

    return exp, log

# 생성 다항식 생성
def generate_generator_polynomial(nsym, exp, log):
    g = [1]
    for i in range(nsym):
        g = poly_mult(g, [1, exp[i]], exp, log)
    return g

# 다항식 곱셈
def poly_mult(p1, p2, exp, log):
    res = [0] * (len(p1) + len(p2) - 1)
    for i in range(len(p1)):
        for j in range(len(p2)):
            if p1[i] != 0 and p2[j] != 0:
                res[i + j] ^= exp[(log[p1[i]] + log[p2[j]]) % 255]
    return res

# 다항식 나눗셈
def poly_div(dividend, divisor, exp, log):
    msg_out = list(dividend)  # 나눗셈 결과 초기화
    for i in range(len(dividend) - (len(divisor) - 1)):
        coef = msg_out[i]
        if coef != 0:
            for j in range(1, len(divisor)):
                if divisor[j] != 0:
                    msg_out[i + j] ^= exp[(log[coef] + log[divisor[j]]) % 255]
    return msg_out[-(len(divisor) - 1):]

# 에러 정정 코드워드 생성
def rs_encode_msg(msg_in, nsym):
    exp, log = init_galois_field()
    gen = generate_generator_polynomial(nsym, exp, log)
    msg_out = [0] * (len(msg_in) + nsym)
    msg_out[:len(msg_in)] = msg_in
    remainder = poly_div(msg_out, gen, exp, log)
    return msg_in + remainder