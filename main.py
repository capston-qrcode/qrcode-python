import re
import csv
import math
from PIL import Image

import copy

from reedsolo import RSCodec

def determine_mode(data):
    if re.match(r'^[0-9]+$', data):
        return 'Numeric'
    elif re.match(r'^[0-9A-Z $%*+\-./:]+$', data):
        return 'Alphanumeric'
    else:
        return 'Byte'

def get_version(data_length, mode, ecc_level):
    for version, capacity in enumerate(qr_capacity[ecc_level], start=1):
        if mode == 'Numeric':
            b_length = 4 + get_char_count_indicator_length(version, mode) + 10 * (data_length // 3)
            if data_length % 3 == 0:
                b_length += 0
            elif data_length % 3 == 1:
                b_length += 4
            elif data_length % 3 == 2:
                b_length += 7
            if b_length <= capacity:
                return version
        elif mode == 'Alphanumeric':
            b_length = 4 + get_char_count_indicator_length(version, mode) + 11 * (data_length // 2) + 6 * (data_length % 2)
            if b_length <= capacity:
                return version
        elif mode == 'Byte':
            b_length = 16 + get_char_count_indicator_length(version, mode) + 8 * data_length
            if b_length <= capacity:
                return version
    return None

def get_char_count_indicator_length(version, mode):
    if 1 <= version <= 9:
        if mode == 'Numeric':
            return 10
        elif mode == 'Alphanumeric':
            return 9
        elif mode == 'Byte':
            return 8
    elif 10 <= version <= 26:
        if mode == 'Numeric':
            return 12
        elif mode == 'Alphanumeric':
            return 11
        elif mode == 'Byte':
            return 16
    elif 27 <= version <= 40:
        if mode == 'Numeric':
            return 14
        elif mode == 'Alphanumeric':
            return 13
        elif mode == 'Byte':
            return 16
    return None


def add_terminator_and_pad(encoded_data, total_bits):
    for _ in range(min(4, total_bits - len(encoded_data))):
        encoded_data += '0'

    while len(encoded_data) % 8 != 0:
        encoded_data += '0'

    rest = len(encoded_data) % 8
    if rest:
        for _ in range(8 - rest):
            encoded_data += '0'

    padding_patterns = ['11101100', '00010001']
    bytes_to_fill = (total_bits - len(encoded_data)) // 8
    for i in range(bytes_to_fill):
        encoded_data += padding_patterns[i % 2]
    return encoded_data

def encode_data(data, ecc_level='M'):
    mode = determine_mode(data)

    mode_indicators = {
        'Numeric': '0001',
        'Alphanumeric': '0010',
        'Byte': '0100'
    }

    encoded_data = mode_indicators[mode]

    data_length = len(data)

    version = get_version(data_length, mode, ecc_level)
    if version is None:
        raise ValueError("데이터가 너무 길어서 모든 버전에 맞지 않습니다.")

    char_count_indicator_length = get_char_count_indicator_length(version, mode)
    if char_count_indicator_length is None:
        raise ValueError("문자 카운트 지시자의 길이를 결정할 수 없습니다.")

    encoded_data += format(data_length, f'0{char_count_indicator_length}b')

    if mode == 'Numeric':
        for i in range(0, data_length, 3):
            group = data[i:i + 3]
            encoded_data += format(int(group), f'0{len(group) * 3 + 1}b')
    elif mode == 'Alphanumeric':
        alphanumeric_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'
        for i in range(0, data_length, 2):
            if i + 1 < data_length:
                pair = data[i:i + 2]
                value = alphanumeric_chars.index(pair[0]) * 45 + alphanumeric_chars.index(pair[1])
                encoded_data += format(value, '011b')
            else:
                value = alphanumeric_chars.index(data[i])
                encoded_data += format(value, '06b')
    elif mode == 'Byte':
        encoded_data = '011100011010' + encoded_data
        for char in data:
            for byte in char.encode('utf-8'):
                encoded_data += format(byte, '08b')

    encoded_data = add_terminator_and_pad(encoded_data, qr_capacity[ecc_level][version - 1])

    return version, encoded_data



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
def rs_encode_msg(msg_in, nsym, exp, log):
    gen = generate_generator_polynomial(nsym, exp, log)
    msg_out = [0] * (len(msg_in) + nsym)
    msg_out[:len(msg_in)] = msg_in
    remainder = poly_div(msg_out, gen, exp, log)

    # rsc = RSCodec(nsym)
    # full_codewords = rsc.encode(msg_in)
    # print(f'rsc: {list(full_codewords)[-nsym:] == remainder}')
    return msg_in + remainder

def make_data_with_reed_solomon(encoded_data, error_blocks):
    data_idx = 0
    data_code = []
    error_code = []

    max_data_length = 0
    max_error_data_length = 0
    additional_blocks = 0
    for error_block in error_blocks:
        total_count, data_count, error_count = error_block
        error_count = total_count - data_count

        # additional_blocks += total_count - (data_count + 2 * error_count)

        max_data_length = max(max_data_length, data_count)
        max_error_data_length = max(max_error_data_length, error_count)

        target_data = []
        for idx in range(data_count):
            data = encoded_data[data_idx:data_idx + 8]
            target_data.append(data)
            data_idx += 8
        rs_data = rs_encode_msg([int(d, 2) for d in target_data], error_count, exp, log)
        rs_data = rs_data[len(target_data):]

        data_code.append(target_data)
        error_code.append([format(d, '08b') for d in rs_data])

    data_block = []
    for i in range(max_data_length):
        for d in data_code:
            if i < len(d):
                data_block.append(d[i])
    for i in range(max_error_data_length):
        for d in error_code:
            if i < len(d):
                data_block.append(d[i])
    for _ in range(additional_blocks):
        data_block.append('00000000')

    print('데이터 블록 개수:', sum([len(d) for d in data_code]))
    print('에러 블록 개수:', sum([len(d) for d in error_code]))
    print('추가 블록 개수:', additional_blocks)
    print('총 블록 개수:', len(data_block))

    return data_block


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


def add_finder_pattern(modules, module_count, start_x, start_y):
    for i in range(start_y - 1, start_y + 8):
        for j in range(start_x - 1, start_x + 8):
            if 0 <= i < module_count and 0 <= j < module_count:
                if i == start_y - 1 or i == start_y + 7:
                    modules[i][j] = 0
                elif j == start_x - 1 or j == start_x + 7:
                    modules[i][j] = 0
    for i in range(start_y, start_y + 7):
        for j in range(start_x, start_x + 7):
            if i == start_y or i == start_y + 6:
                modules[i][j] = 1
            elif j == start_x or j == start_x + 6:
                modules[i][j] = 1
    for i in range(start_y + 1, start_y + 6):
        for j in range(start_x + 1, start_x + 6):
            if i == start_y + 1 or i == start_y + 5:
                modules[i][j] = 0
            elif j == start_x + 1 or j == start_x + 5:
                modules[i][j] = 0
    for i in range(start_y + 2, start_y + 5):
        for j in range(start_x + 2, start_x + 5):
            modules[i][j] = 1

def add_align_pattern(modules, version):
    pos = align_pattern_pos[version - 1]
    for i in range(len(pos)):
        row = pos[i]
        for j in range(len(pos)):
            col = pos[j]
            if modules[row][col] != 2:
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    if r == -2 or r == 2 or c == -2 or c == 2 or (r == 0 and c == 0):
                        modules[row + r][col + c] = 1
                    else:
                        modules[row + r][col + c] = 0

def add_timing_pattern(modules, module_count):
    for i in range(8, module_count - 8):
        if modules[i][6] != 2: continue
        modules[i][6] = int(i % 2 == 0)
    for i in range(8, module_count - 8):
        if modules[6][i] != 2: continue
        modules[6][i] = int(i % 2 == 0)

def add_version_information(modules, module_count, version):
    version_bits = format(version, '06b')
    version_bits += bch_encode(version, 18, 6, [1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 1])
    print('버전 비트:', version_bits)
    bits_idx = 0
    for i in range(0, 6):
        for j in range(module_count - 11, module_count - 8):
            modules[j][i] = int(version_bits[bits_idx])
            modules[i][j] = int(version_bits[bits_idx])
            bits_idx += 1

def add_data_with_mask(modules, module_count, mask_func, data):
    print('map data:', [int(i, 2) for i in data])
    direction_y = -1
    x = module_count - 1
    y = module_count - 1

    width, height = 4 * module_count, 4 * module_count
    image = Image.new('L', (32 + width, 32 + height))
    pixels = image.load()

    for i in range(32 + width):
        for j in range(32 + height):
            pixels[i, j] = 255

    alpha = [55, 80, 105, 130, 155, 180, 205, 230]
    for idx, block in enumerate(data):
        bit_idx = 0
        while bit_idx <= 7:
            if modules[y][x] == 2:
                for p_i in range(x * 4 + 16, x * 4 + 20):
                    for p_j in range(y * 4 + 16, y * 4 + 20):
                        pixels[p_i, p_j] = alpha[bit_idx]

                target_bit = int(block[bit_idx])
                if mask_func(y, x):
                    target_bit ^= 1
                modules[y][x] = target_bit
                # modules[y][x] = alpha
                bit_idx += 1
            if (x % 2 == 0) ^ (x <= 6):
                x -= 1
            else:
                x += 1
                y += direction_y
                if y < 0:
                    direction_y = 1
                    y = 0
                    x -= 2
                elif y >= module_count:
                    direction_y = -1
                    y = module_count - 1
                    x -= 2
            if x == 6:
                x -= 1

        # image.save(f'./image/qr_blocks_{idx}.png')
    image.save(f'./image/qr_blocks.png')
    return modules

def add_format_information_with_mask(modules, module_count, mask_bit, error_bit):
    format_bit = error_bit + mask_bit
    format_bit += bch_encode(int(format_bit, 2), 15, 5, [1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1])
    format_bit = [int(b) for b in format_bit]
    print('format bits:', ''.join([str(i) for i in format_bit]))
    mask = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0]
    for i in range(15):
        format_bit[i] = format_bit[i] ^ mask[i]
    print('masked format bits:', ''.join([str(i) for i in format_bit]))

    bit_idx = 14
    for i in range(0, 9):
        if i == 6: continue
        modules[i][8] = format_bit[bit_idx]
        bit_idx -= 1
    for i in range(7, -1, -1):
        if i == 6: continue
        modules[8][i] = format_bit[bit_idx]
        bit_idx -= 1

    bit_idx = 14
    for i in range(module_count - 1, module_count - 9, -1):
        if i == module_count - 8:
            modules[8][i] = 1
            continue
        modules[8][i] = format_bit[bit_idx]
        bit_idx -= 1
    for i in range(module_count - 8, module_count):
        modules[i][8] = format_bit[bit_idx]
        bit_idx -= 1
    return modules

def evaluate_mask(modules, module_count):
    penalty = 0

    # Rule 1: 연속된 같은 색 모듈 검출
    for i in range(module_count):
        row_count = 1
        col_count = 1
        for j in range(1, module_count):
            # 행 방향으로 연속된 모듈
            if modules[i][j] == modules[i][j - 1]:
                row_count += 1
            else:
                if row_count >= 5:
                    penalty += (row_count - 2)
                row_count = 1
            # 열 방향으로 연속된 모듈
            if modules[j][i] == modules[j - 1][i]:
                col_count += 1
            else:
                if col_count >= 5:
                    penalty += (col_count - 2)
                col_count = 1
        if row_count >= 5:
            penalty += (row_count - 2)
        if col_count >= 5:
            penalty += (col_count - 2)

    # Rule 2: 2x2 블록 패턴 검출
    for i in range(module_count - 1):
        for j in range(module_count - 1):
            if modules[i][j] == modules[i][j + 1] == modules[i + 1][j] == modules[i + 1][j + 1]:
                penalty += 3

    # Rule 3: 1:1:3:1:1 패턴 검출
    def check_pattern(arr):
        return (arr[0] == arr[1] and
                arr[1] != arr[2] and
                arr[2] == arr[3] == arr[4] and
                arr[4] != arr[5] and
                arr[5] == arr[6])

    for i in range(module_count):
        for j in range(module_count - 6):
            row_pattern = modules[i][j:j + 7]
            col_pattern = [modules[j + k][i] for k in range(7)]
            if check_pattern(row_pattern):
                penalty += 40
            if check_pattern(col_pattern):
                penalty += 40

    # Rule 4: 전체 모듈의 흑백 비율
    total_modules = module_count * module_count
    dark_modules = sum(row.count(1) for row in modules)
    k = abs(dark_modules * 2 - total_modules) // total_modules
    penalty += k * 10

    return penalty

def make_qrcode(data, ecc_level, version):
    module_count = version * 4 + 17
    modules = [[2] * module_count for _ in range(module_count)]
    add_finder_pattern(modules, module_count, 0, 0)
    add_finder_pattern(modules, module_count, module_count - 7, 0)
    add_finder_pattern(modules, module_count, 0, module_count - 7)
    add_align_pattern(modules, version)
    add_timing_pattern(modules, module_count)

    if version >= 7:
        add_version_information(modules, module_count, version)

    min_penalty = 1e10
    min_mask = 0
    min_module = []
    for mask_bit in mask_bits:
        mask_f = mask_func[mask_bit]
        option = copy.deepcopy(modules)
        option = add_format_information_with_mask(option, module_count, mask_bit, error_level_to_bit[ecc_level])
        option = add_data_with_mask(option, module_count, mask_f, data)
        penalty = evaluate_mask(option, module_count)
        if penalty < min_penalty:
            print('low')
            min_penalty = penalty
            min_module = option
            min_mask = mask_bit
    print(f'선택된 마스크: {min_mask} 패널티: {min_penalty}')
    # for m in min_module:
    #     print(*m)

    width, height = 4 * module_count, 4 * module_count
    image = Image.new('1', (32 + width, 32 + height))
    pixels = image.load()

    for i in range(32 + width):
        for j in range(32 + height):
            pixels[i, j] = 1

    for i in range(module_count):
        for j in range(module_count):
            for p_i in range(i * 4 + 16, i * 4 + 20):
                for p_j in range(j * 4 + 16, j * 4 + 20):
                    pixels[p_j, p_i] = 1 - min_module[i][j]
    return image


if __name__ == '__main__':
    qr_capacity = {
        'L': [],
        'M': [],
        'Q': [],
        'H': []
    }
    with open('size.csv', mode='r') as file:
        reader = csv.reader(file)
        attrs = []
        for row in reader:
            if len(attrs) < 1:
                attrs = row
                continue
            for key, value in zip(attrs, row):
                qr_capacity[key].append(int(value))

    error_block_info = {
        'L': [
            (1, 26, 19, 2),
            (1, 44, 34, 4),
            (1, 70, 55, 7),
            (1, 100, 80, 10),
            (1, 134, 108, 13),
            (2, 86, 68, 9),
            (2, 98, 78, 10),
            (2, 121, 97, 12),
            (2, 146, 116, 15),
            (2, 86, 68, 9, 2, 87, 69, 9),
            (4, 101, 81, 10),
            (2, 116, 92, 12, 2, 117, 93, 12),
            (4, 133, 107, 13),
            (3, 145, 115, 15, 1, 146, 116, 15),
            (5, 109, 87, 11, 1, 110, 88, 11),
            (5, 122, 98, 12, 1, 123, 99, 12),
            (1, 135, 107, 14, 5, 136, 108, 14),
            (5, 150, 120, 15, 1, 151, 121, 15),
            (3, 141, 113, 14, 4, 142, 114, 14),
            (3, 135, 107, 14, 5, 136, 108, 14),
            (4, 144, 116, 14, 4, 145, 117, 14),
            (2, 139, 111, 14, 7, 140, 112, 14),
            (4, 151, 121, 15, 5, 152, 122, 15),
            (6, 147, 117, 15, 4, 148, 118, 15),
            (8, 132, 106, 13, 4, 133, 107, 13),
            (10, 142, 114, 14, 2, 143, 115, 14),
            (8, 152, 122, 15, 4, 153, 123, 15),
            (3, 147, 117, 15, 10, 148, 118, 15),
            (7, 146, 116, 15, 7, 147, 117, 15),
            (5, 145, 115, 15, 10, 146, 116, 15),
            (13, 145, 115, 15, 3, 146, 116, 15),
            (17, 145, 115, 15),
            (17, 145, 115, 15, 1, 146, 116, 15),
            (13, 145, 115, 15, 6, 146, 116, 15),
            (12, 151, 121, 15, 7, 152, 122, 15),
            (6, 151, 121, 15, 14, 152, 122, 15),
            (17, 152, 122, 15, 4, 153, 123, 15),
            (4, 152, 122, 15, 18, 153, 123, 15),
            (20, 147, 117, 15, 4, 148, 118, 15),
            (19, 148, 118, 15, 6, 149, 119, 15),
        ],
        'M': [
            (1, 26, 16, 4),
            (1, 44, 28, 8),
            (1, 70, 44, 13),
            (2, 50, 32, 9),
            (2, 67, 43, 12),
            (4, 43, 27, 8),
            (4, 49, 31, 9),
            (2, 60, 38, 11, 2, 61, 39, 11),
            (3, 58, 36, 11, 2, 59, 37, 11),
            (4, 69, 43, 13, 1, 70, 44, 13),
            (1, 80, 50, 15, 4, 81, 51, 15),
            (6, 58, 36, 11, 2, 59, 37, 11),
            (8, 59, 37, 11, 1, 60, 38, 11),
            (4, 64, 40, 12, 5, 65, 41, 12),
            (5, 65, 41, 12, 5, 66, 42, 12),
            (7, 73, 45, 14, 3, 74, 46, 14),
            (10, 74, 46, 14, 1, 75, 47, 14),
            (9, 69, 43, 13, 4, 70, 44, 13),
            (3, 70, 44, 13, 11, 71, 45, 13),
            (3, 67, 41, 13, 13, 68, 42, 13),
            (17, 68, 42, 13),
            (17, 74, 46, 14),
            (4, 75, 47, 14, 14, 76, 48, 14),
            (6, 73, 45, 14, 14, 74, 46, 14),
            (8, 75, 47, 14, 13, 76, 48, 14),
            (19, 74, 46, 14, 4, 75, 47, 14),
            (22, 73, 45, 14, 3, 74, 46, 14),
            (3, 73, 45, 14, 23, 74, 46, 14),
            (21, 73, 45, 14, 7, 74, 46, 14),
            (19, 75, 47, 14, 10, 76, 48, 14),
            (2, 74, 46, 14, 29, 75, 47, 14),
            (10, 74, 46, 14, 23, 75, 47, 14),
            (14, 74, 46, 14, 21, 75, 47, 14),
            (14, 74, 46, 14, 23, 75, 47, 14),
            (12, 75, 47, 14, 26, 76, 48, 14),
            (6, 75, 47, 14, 34, 76, 48, 14),
            (29, 74, 46, 14, 14, 75, 47, 14),
            (13, 74, 46, 14, 32, 75, 47, 14),
            (40, 75, 47, 14, 7, 76, 48, 14),
            (18, 75, 47, 14, 31, 76, 48, 14),
        ],
        'Q': [
            (1, 26, 13, 6),
            (1, 44, 22, 11),
            (2, 35, 17, 9),
            (2, 50, 24, 13),
            (2, 33, 15, 9, 2, 34, 16, 9),
            (4, 43, 19, 12),
            (2, 32, 14, 9, 4, 33, 15, 9),
            (4, 40, 18, 11, 2, 41, 19, 11),
            (4, 36, 16, 10, 4, 37, 17, 10),
            (6, 43, 19, 12, 2, 44, 20, 12),
            (4, 50, 22, 14, 4, 51, 23, 14),
            (4, 46, 20, 13, 6, 47, 21, 13),
            (8, 44, 20, 12, 4, 45, 21, 12),
            (11, 36, 16, 10, 5, 37, 17, 10),
            (5, 54, 24, 15, 7, 55, 25, 15),
            (15, 43, 19, 12, 2, 44, 20, 12),
            (1, 50, 22, 14, 15, 51, 23, 14),
            (17, 50, 22, 14, 1, 51, 23, 14),
            (17, 47, 21, 13, 4, 48, 22, 13),
            (15, 54, 24, 15, 5, 55, 25, 15),
            (17, 50, 22, 14, 6, 51, 23, 14),
            (7, 54, 24, 15, 16, 55, 25, 15),
            (11, 54, 24, 15, 14, 55, 25, 15),
            (11, 54, 24, 15, 16, 55, 25, 15),
            (7, 54, 24, 15, 22, 55, 25, 15),
            (28, 50, 22, 14, 6, 51, 23, 14),
            (8, 53, 23, 15, 26, 54, 24, 15),
            (4, 54, 24, 15, 31, 55, 25, 15),
            (1, 53, 23, 15, 37, 54, 24, 15),
            (15, 54, 24, 15, 25, 55, 25, 15),
            (42, 54, 24, 15, 1, 55, 25, 15),
            (10, 54, 24, 15, 35, 55, 25, 15),
            (29, 54, 24, 15, 19, 55, 25, 15),
            (44, 54, 24, 15, 7, 55, 25, 15),
            (39, 54, 24, 15, 14, 55, 25, 15),
            (46, 54, 24, 15, 10, 55, 25, 15),
            (49, 54, 24, 15, 10, 55, 25, 15),
            (48, 54, 24, 15, 14, 55, 25, 15),
            (43, 54, 24, 15, 22, 55, 25, 15),
            (34, 54, 24, 15, 34, 55, 25, 15),
        ],
        'H': [
            (1, 26, 9, 8),
            (1, 44, 16, 14),
            (2, 35, 13, 11),
            (4, 25, 9, 8),
            (2, 33, 11, 11, 2, 34, 12, 11),
            (4, 43, 15, 14),
            (4, 39, 13, 13, 1, 40, 14, 13),
            (4, 40, 14, 13, 2, 41, 15, 13),
            (4, 36, 12, 12, 4, 37, 13, 12),
            (6, 43, 15, 14, 2, 44, 16, 14),
            (3, 36, 12, 12, 8, 37, 13, 12),
            (7, 42, 14, 14, 4, 43, 15, 14),
            (12, 33, 11, 11, 4, 34, 12, 11),
            (11, 36, 12, 12, 5, 37, 13, 12),
            (11, 36, 12, 12, 7, 37, 13, 12),
            (3, 45, 15, 15, 13, 46, 16, 15),
            (2, 42, 14, 14, 17, 43, 15, 14),
            (2, 42, 14, 14, 19, 43, 15, 14),
            (9, 39, 13, 13, 16, 40, 14, 13),
            (15, 43, 15, 14, 10, 44, 16, 14),
            (19, 46, 16, 15, 6, 47, 17, 15),
            (34, 37, 13, 12),
            (16, 45, 15, 15, 14, 46, 16, 15),
            (30, 46, 16, 15, 2, 47, 17, 15),
            (22, 45, 15, 15, 13, 46, 16, 15),
            (33, 46, 16, 15, 4, 47, 17, 15),
            (12, 45, 15, 15, 28, 46, 16, 15),
            (11, 45, 15, 15, 31, 46, 16, 15),
            (19, 45, 15, 15, 26, 46, 16, 15),
            (23, 45, 15, 15, 25, 46, 16, 15),
            (23, 45, 15, 15, 28, 46, 16, 15),
            (19, 45, 15, 15, 35, 46, 16, 15),
            (11, 45, 15, 15, 46, 46, 16, 15),
            (59, 46, 16, 15, 1, 47, 17, 15),
            (22, 45, 15, 15, 41, 46, 16, 15),
            (2, 45, 15, 15, 64, 46, 16, 15),
            (24, 45, 15, 15, 46, 46, 16, 15),
            (42, 45, 15, 15, 32, 46, 16, 15),
            (10, 45, 15, 15, 67, 46, 16, 15),
            (20, 45, 15, 15, 61, 46, 16, 15),
        ]
    }

    align_pattern_pos = [
        [],
        [6, 18],
        [6, 22],
        [6, 26],
        [6, 30],
        [6, 34],
        [6, 22, 38],
        [6, 24, 42],
        [6, 26, 46],
        [6, 28, 50],
        [6, 30, 54],
        [6, 32, 58],
        [6, 34, 62],
        [6, 26, 46, 66],
        [6, 26, 48, 70],
        [6, 26, 50, 74],
        [6, 30, 54, 78],
        [6, 30, 56, 82],
        [6, 30, 58, 86],
        [6, 34, 62, 90],
        [6, 28, 50, 72, 94],
        [6, 26, 50, 74, 98],
        [6, 30, 54, 78, 102],
        [6, 28, 54, 80, 106],
        [6, 32, 58, 84, 110],
        [6, 30, 58, 86, 114],
        [6, 34, 62, 90, 118],
        [6, 26, 50, 74, 98, 122],
        [6, 30, 54, 78, 102, 126],
        [6, 26, 52, 78, 104, 130],
        [6, 30, 56, 82, 108, 134],
        [6, 34, 60, 86, 112, 138],
        [6, 30, 58, 86, 114, 142],
        [6, 34, 62, 90, 118, 146],
        [6, 30, 54, 78, 102, 126, 150],
        [6, 24, 50, 76, 102, 128, 154],
        [6, 28, 54, 80, 106, 132, 158],
        [6, 32, 58, 84, 110, 136, 162],
        [6, 26, 54, 82, 110, 138, 166],
        [6, 30, 58, 86, 114, 142, 170],
    ]

    # mask_bits = ['000', '001', '010', '011', '100', '101', '110', '111']
    mask_bits = ['010']
    mask_func = {
        '000': lambda i, j: (i + j) % 2 == 0,
        '001': lambda i, j: i % 2 == 0,
        '010': lambda i, j: j % 3 == 0,
        '011': lambda i, j: (i + j) % 3 == 0,
        '100': lambda i, j: (i // 2 + j // 3) % 2 == 0,
        '101': lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
        '110': lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
        '111': lambda i, j: ((i * j) % 3 + (i + j) % 2) % 2 == 0,
    }

    error_level_to_bit = {
        'L': '01',
        'M': '00',
        'Q': '11',
        'H': '10'
    }

    exp, log = init_galois_field()

    test_data = [
        ('안녕하세요.dsjlkl_ndjks7&&83', 'M'),
        ('https://qrfy.com/?utm_source=Google&utm_medium=CPC&utm_campaign=17680026409&utm_term=qr%20code%20maker&gad_source=1&gclid=Cj0KCQjwkdO0BhDxARIsANkNcrfErfu3V0ztbOAN2_YjxlhdNhLMmjzDfHouAZIx5kZNfoDHi9wHCYoaAmDlEALw_wcB', 'M'),
        ('010-0000-0000', 'M'),
        ('AC-42', 'H'),
        ('01234567890123450123456789012345', 'H')
    ]

    for data_idx, d in enumerate(test_data):
        data, ecc_level = d
        version, encoded_data = encode_data(data, ecc_level)
        print('원본 데이터:', data)
        print('버전:', version)
        print('ecc level:', ecc_level)
        print('인코딩 데이터:', encoded_data)
        print('인코딩 데이터 길이:', len(encoded_data))

        error_blocks = []
        error_block_size = error_block_info[ecc_level][version - 1]
        print('error block size info:', error_block_size)
        for i in range(0, len(error_block_size), 4):
            block_count, total_count, data_count, error_count = error_block_size[i:i + 4]
            for idx in range(block_count):
                error_blocks.append((total_count, data_count, error_count))

        merged_data = make_data_with_reed_solomon(encoded_data, error_blocks)
        qr_image = make_qrcode(merged_data, ecc_level, version)
        qr_image.save(f'./image/{data_idx}_qr.png')
        # qr_image.show()

        print()
