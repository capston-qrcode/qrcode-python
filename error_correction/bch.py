def gf_mult(x, y, prim=0b1011, field_charac_full=1 << 4):
    r = 0
    while y:
        if y & 1:
            r ^= x
        x <<= 1
        if x & field_charac_full:
            x ^= prim
        y >>= 1
    return r


def gf_poly_div(dividend, divisor):
    result = list(dividend)
    for i in range(len(dividend) - len(divisor) + 1):
        coef = result[i]
        if coef != 0:
            for j in range(1, len(divisor)):
                result[i + j] ^= gf_mult(divisor[j], coef)
    return result[-(len(divisor) - 1):]

def bch_encode(data_int, n, k, gen_poly):
    data_poly = [int(bit) for bit in bin(data_int)[2:]]
    data_poly += [0] * (n - k)

    rem = gf_poly_div(data_poly, gen_poly)
    return ''.join(str(bit) for bit in rem)