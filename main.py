import re
import csv

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
    terminator = '0000'
    if len(encoded_data) + 4 <= total_bits:
        encoded_data += terminator
    else:
        encoded_data += '0' * (total_bits - len(encoded_data))

    while len(encoded_data) % 8 != 0:
        encoded_data += '0'

    padding_patterns = ['11101100', '00010001']
    i = 0
    while len(encoded_data) < total_bits:
        encoded_data += padding_patterns[i % 2]
        i += 1

    return encoded_data[:total_bits]

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

        additional_blocks += total_count - (data_count + 2 * error_count)

        max_data_length = max(max_data_length, data_count)
        max_error_data_length = max(max_error_data_length, error_count * 2)

        target_data = []
        for idx in range(data_count):
            data = encoded_data[data_idx:data_idx + 8]
            target_data.append(data)
            data_idx += 8
        rs_data = rs_encode_msg([int(d, 2) for d in target_data], error_count * 2, exp, log)
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


def add_finder_pattern(modules, start_x, start_y):
    for i in range(start_y, start_y + 7):
        for j in range(start_x, start_x + 7):
            if i == start_y or i == start_y + 6:
                modules[i][j] = 1
            elif j == start_x or j == start_x + 6:
                modules[i][j] = 1
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

def make_qrcode(data, ecc_level, version):
    module_count = version * 4 + 17
    modules = [[2] * module_count for _ in range(module_count)]
    add_finder_pattern(modules, 0, 0)
    add_finder_pattern(modules, module_count - 7, 0)
    add_finder_pattern(modules, 0, module_count - 7)
    add_align_pattern(modules, version)
    add_timing_pattern(modules, module_count)

    print(modules)
    for m in modules:
        print(''.join([str(i) for i in m]))


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

    exp, log = init_galois_field()

    test_data = [
        ('안녕하세요.dsjlkl_ndjks7&&83', 'M'),
        ('https://qrfy.com/?utm_source=Google&utm_medium=CPC&utm_campaign=17680026409&utm_term=qr%20code%20maker&gad_source=1&gclid=Cj0KCQjwkdO0BhDxARIsANkNcrfErfu3V0ztbOAN2_YjxlhdNhLMmjzDfHouAZIx5kZNfoDHi9wHCYoaAmDlEALw_wcB', 'M'),
        ('010-0000-0000', 'M'),
        ('AC-42', 'H'),
        ('01234567890123450123456789012345', 'H')
    ]

    for data, ecc_level in test_data:
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
        make_qrcode(merged_data, ecc_level, version)

        print()
