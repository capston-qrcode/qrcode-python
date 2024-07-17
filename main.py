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

    return version, encoded_data

if __name__ == '__main__':
    print(encode_data('안녕하세요.'))
    print(encode_data('010-0000-0000'))
    print(encode_data('AC-42', ecc_level='H'))
    print(encode_data('01234567', ecc_level='H'))
    print(encode_data('0123456789012345', ecc_level='H'))
