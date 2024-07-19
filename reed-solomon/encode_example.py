# 유한체의 덧셈
def gf_add(x, y):
    return x ^ y  # GF(2^m)에서 덧셈은 XOR 연산으로 수행됩니다.


# 유한체의 곱셈
def gf_mult(x, y, prim=0x11b, field_charac_full=256):
    # GF(2^8)에서의 곱셈을 수행합니다.
    r = 0
    while y:
        if y & 1:
            r ^= x
        x <<= 1
        if x & field_charac_full:
            x ^= prim
        y >>= 1
    return r


# 유한체의 역원 계산
def gf_inv(x, prim=0x11b, field_charac_full=256):
    # GF(2^8)에서의 역원을 계산합니다.
    for i in range(1, field_charac_full):
        if gf_mult(x, i, prim) == 1:
            return i
    return 0


# 다항식의 나머지 계산
def gf_poly_div(dividend, divisor):
    # 다항식 나눗셈을 수행하여 나머지를 계산합니다.
    result = list(dividend)
    for i in range(len(dividend) - len(divisor) + 1):
        coef = result[i]
        if coef != 0:
            for j in range(1, len(divisor)):
                result[i + j] ^= gf_mult(divisor[j], coef)
    return result[-(len(divisor) - 1):]


# 패리티 심볼 생성
def rs_encode_msg(msg_in, nsym):
    # 주어진 메시지에 대해 Reed-Solomon 코드의 패리티 심볼을 생성합니다.
    gen = [1]
    for i in range(nsym):
        gen = [gf_mult(g, 2) for g in gen] + [0]
        for j in range(len(gen) - 1, 0, -1):
            gen[j] ^= gen[j - 1]

    msg_out = list(msg_in) + [0] * nsym
    rem = gf_poly_div(msg_out, gen)

    msg_out[-nsym:] = rem
    return msg_out


# 예제 메시지 및 패리티 심볼 생성
msg = [32, 91, 11, 0, 22, 43, 87, 5]
nsym = 4
encoded_msg = rs_encode_msg(msg, nsym)

print('origin msg:', msg)
print("Encoded Message: ", encoded_msg)