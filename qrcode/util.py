import re
import qrcode.constants as constants

def determine_mode(data):
    '''
    입력된 데이터로 qr코드 모드 결정하는 함수
    :param data: 입력 데이터
    :return: 모드 string
    '''
    if re.match(r'^[0-9]+$', data):
        return 'Numeric'
    elif re.match(r'^[0-9A-Z $%*+\-./:]+$', data):
        return 'Alphanumeric'
    else:
        return 'Byte'

def get_char_count_indicator_length(version, mode):
    '''
    버전별 데이터 길이 표현 비트 수 결정하는 함수
    :param version: qr코드 버전
    :param mode: qr코드 모드
    :return: 데이터 길이 비트 길이 수
    '''
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

def get_version(data_length, mode, ecc_level):
    '''
    입력된 데이터의 길이로 qr코드 버전을 결정하는 함수
    :param data_length: 데이터 길이
    :param mode: qr코드 모드
    :param ecc_level: qr코드 오류 정정 레벨
    :return: 버전 int
    '''

    # 사전 정의된 모드 - 오류 정정 레벨별 최대 저장 가능 비트 정보로 버전별 반복
    for version, capacity in enumerate(constants.QRCODE_CAPACITY[ecc_level], start=1):
        if mode == 'Numeric':
            # Numeric 모드 비트 수 계산
            b_length = 4 + get_char_count_indicator_length(version, mode) + 10 * (data_length // 3)
            if data_length % 3 == 0:
                b_length += 0
            elif data_length % 3 == 1:
                b_length += 4
            elif data_length % 3 == 2:
                b_length += 7
            # 데이터를 표현 가능한 최소 버전이라면 리턴
            if b_length <= capacity:
                return version
        elif mode == 'Alphanumeric':
            # Alphanumeric 모드 비트 수 계산
            b_length = 4 + get_char_count_indicator_length(version, mode) + 11 * (data_length // 2) + 6 * (data_length % 2)
            # 데이터를 표현 가능한 최소 버전이라면 리턴
            if b_length <= capacity:
                return version
        elif mode == 'Byte': # utf-8
            # Byte 모드 비트 수 계산
            b_length = 16 + get_char_count_indicator_length(version, mode) + 8 * data_length
            # 데이터를 표현 가능한 최소 버전이라면 리턴
            if b_length <= capacity:
                return version
    # 모두 데이터를 표현할 수 없다면 오류
    raise ValueError('데이터 길이가 너무 길어서 모든 버전에 맞지 않습니다.')

def add_terminator_and_pad(encoded_data, total_bits):
    '''
    인코드 데이터에 종단자/패딩 비트 추가하는 함수
    :param encoded_data: 인코드 데이터
    :param total_bits: qr코드의 총 비트 수
    :return: 종단자/패딩 비트가 추가된 인코드 데이터
    '''

    # 남은 비트 수가 4개 이하면 남은 수 만큼 0 추가
    for _ in range(min(4, total_bits - len(encoded_data))):
        encoded_data += '0'

    # 8 비트 단위로 끊을 수 있도록 0 비트 추가
    while len(encoded_data) % 8 != 0:
        encoded_data += '0'

    # 두 패딩 비트를 번갈아 가며 총 비트 수에 맞게 추가
    padding_patterns = ['11101100', '00010001']
    bytes_to_fill = (total_bits - len(encoded_data)) // 8
    for i in range(bytes_to_fill):
        encoded_data += padding_patterns[i % 2]
    return encoded_data

def evaluate_mask(modules, module_count):
    '''
    마스크가 적용해서 생성이 완료된 qr코드의 패널티를 계산하는 함수
    :param modules: qr코드 2darray
    :param module_count: 모듈 개수
    :return: 패널티 점수
    '''
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
