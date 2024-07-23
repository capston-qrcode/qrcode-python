from PIL import Image
import copy
import re

import error_correction.reed_solomon as reed_solomon
import error_correction.bch as bch
import qrcode.constants as constants
import qrcode.util as util

'''
QRCode 클래스
데이터를 QRCode로 바꾸는 클래스
'''

class QRCode(object):
    def __init__(
        self,
        data: str,
        ecc_level=constants.ERROR_LEVEL_M
    ):
        self.data = data
        self.ecc_level = ecc_level

        self.__make__()

    def __add_error_bits__(self):
        '''
        Reed-Solomon 알고리즘으로 에러 정정 비트 추가하는 함수
        '''

        # 정의된 블록 정보에 따라 만들어야 할 오류 정정 코드워드 개수 산출
        error_blocks = []
        error_block_size = constants.ERROR_BLOCK_TABLE[self.ecc_level][self.version - 1]
        for i in range(0, len(error_block_size), 4):
            block_count, total_count, data_count, error_count = error_block_size[i:i + 4]
            for idx in range(block_count):
                error_blocks.append((total_count, data_count, error_count))

        data_idx = 0 # 데이터 idx
        data_code = [] # 데이터 코드워드
        error_code = [] # 에러 정정 코드워드

        max_data_length = 0 # 최대 데이터 코드워드 길이
        max_error_data_length = 0 # 최대 에러 정정 코드워드 길이
        # additional_blocks = 0

        # 에러 정정 코드워드 개수 만큼 반복
        for error_block in error_blocks:
            # 사전 정의된 개수 정보 가져오기
            total_count, data_count, error_count = error_block
            # 에러 코드워드 개수 = 전체 코드워드 - 데이터 코드워드
            error_count = total_count - data_count

            # additional_blocks += total_count - (data_count + 2 * error_count)

            # 최대 데이터 코드워드 길이 업데이트
            max_data_length = max(max_data_length, data_count)
            # 최대 에러 정정 코드워드 길이 업데이트
            max_error_data_length = max(max_error_data_length, error_count)

            # 데이터 코드워드 개수에 맞게 인코딩된 비트 가져오기
            target_data = []
            for idx in range(data_count):
                data = self.encoded_data[data_idx:data_idx + 8]
                target_data.append(data)
                data_idx += 8
            # 데이터 비트에 reed-solomon 에러 정정 비트 추가
            rs_data = reed_solomon.rs_encode_msg([int(d, 2) for d in target_data], error_count)
            # 에러 정정 비트만 추출
            rs_data = rs_data[len(target_data):]

            # 데이터 코드워드 추가
            data_code.append(target_data)
            # 오류 정정 코드워드 추가
            error_code.append([format(d, '08b') for d in rs_data])

        # 블록 리스트
        self.data_block = []
        # 데이터 코드워드를 순회하며 앞 비트부터 순서대로 추가
        for i in range(max_data_length):
            for d in data_code:
                if i < len(d):
                    self.data_block.append(d[i])
        # 오류 정정 코드워드를 순회하며 앞 비트부터 순서대로 추가
        for i in range(max_error_data_length):
            for d in error_code:
                if i < len(d):
                    self.data_block.append(d[i])
        # for _ in range(additional_blocks):
        #     self.data_block.append('00000000')

    def __encode_data__(self):
        '''
        데이터를 비트로 인코딩하는 함수
        '''

        # QR코드 모드 결정
        self.mode = util.determine_mode(self.data)
        # 데이터 길이 저장
        self.data_length = len(self.data)

        # 모드가 바이트일때
        if self.mode == 'Byte':
            # 데이터 utf-8 인코딩
            self.data = self.data.encode('utf-8')
            # 인코딩된 데이터 길이
            self.data_length = len(self.data)

        # 인코드 데이터에 모드 정보 비트로 추가
        self.encoded_data = constants.MODE_BITS[self.mode]
        # qr코드 버전 결정
        self.version = util.get_version(self.data_length, self.mode, self.ecc_level)
        # 데이터 개수 표현 비트 수 가져와서 인코드 데이터에 적용
        char_count_indicator_length = util.get_char_count_indicator_length(self.version, self.mode)
        self.encoded_data += format(self.data_length, f'0{char_count_indicator_length}b')

        # 각 모드에 맞게 데이터 인코딩 후 인코드 데이터에 추가
        if self.mode == 'Numeric':
            for i in range(0, self.data_length, 3):
                group = self.data[i:i + 3]
                self.encoded_data += format(int(group), f'0{len(group) * 3 + 1}b')
        elif self.mode == 'Alphanumeric':
            alphanumeric_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'
            for i in range(0, self.data_length, 2):
                if i + 1 < self.data_length:
                    pair = self.data[i:i + 2]
                    value = alphanumeric_chars.index(pair[0]) * 45 + alphanumeric_chars.index(pair[1])
                    self.encoded_data += format(value, '011b')
                else:
                    value = alphanumeric_chars.index(self.data[i])
                    self.encoded_data += format(value, '06b')
        elif self.mode == 'Byte':  # utf-8
            # encoded_data = '011100011010' + encoded_data
            # encoded_data += '0000'
            for char in self.data:
                self.encoded_data += format(char, '08b')

        # 인코드 데이터에 생성 후 남은 공간에 종단자, 패딩 비트 추가
        self.encoded_data = util.add_terminator_and_pad(
            self.encoded_data, constants.QRCODE_CAPACITY[self.ecc_level][self.version - 1])

    def __add_finder_pattern__(self, modules, start_x, start_y):
        '''
        파인더 패턴을 추가하는 함수
        :param modules: qr코드 2darray
        :param start_x: 가로 시작 위치
        :param start_y: 세로 시작 위치
        '''
        # 파인더 패턴 바깥 분리자 추가
        for i in range(start_y - 1, start_y + 8):
            for j in range(start_x - 1, start_x + 8):
                if 0 <= i < self.module_count and 0 <= j < self.module_count:
                    if i == start_y - 1 or i == start_y + 7:
                        modules[i][j] = 0
                    elif j == start_x - 1 or j == start_x + 7:
                        modules[i][j] = 0
        # 7x7 검정색 패턴 추가
        for i in range(start_y, start_y + 7):
            for j in range(start_x, start_x + 7):
                if i == start_y or i == start_y + 6:
                    modules[i][j] = 1
                elif j == start_x or j == start_x + 6:
                    modules[i][j] = 1
        # 6x6 흰색 패턴 추가
        for i in range(start_y + 1, start_y + 6):
            for j in range(start_x + 1, start_x + 6):
                if i == start_y + 1 or i == start_y + 5:
                    modules[i][j] = 0
                elif j == start_x + 1 or j == start_x + 5:
                    modules[i][j] = 0
        # 5x5 검정색 패턴 추가
        for i in range(start_y + 2, start_y + 5):
            for j in range(start_x + 2, start_x + 5):
                modules[i][j] = 1
                
    def __add_align_pattern__(self, modules):
        '''
        정렬 패턴을 추가하는 함수
        :param modules: qr코드 2darray
        '''
        # 사전 정의된 버전별 정렬 패턴 위치 가져오기
        pos = constants.ALIGN_PATTERN_POSITION[self.version - 1]
        # 정렬 패턴 추가
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

    def __add_timing_pattern__(self, modules):
        '''
        타이밍 패턴을 추가하는 함수
        :param modules: qr코드 2darray
        '''
        # 세로 타이밍 패턴 추가
        for i in range(8, self.module_count - 8):
            if modules[i][6] != 2: continue
            modules[i][6] = int(i % 2 == 0)
        # 가로 타이밍 패턴 추가
        for i in range(8, self.module_count - 8):
            if modules[6][i] != 2: continue
            modules[6][i] = int(i % 2 == 0)

    def __add_version_information__(self, modules):
        '''
        버전 정보를 추가하는 함수
        :param modules: qr코드 2darray
        '''

        # 버전 수 6비트의 이진수로 변환
        version_bits = format(self.version, '06b')
        # bch 알고리즘으로 에러 정정 비트 추가
        version_bits += bch.bch_encode(self.version, 18, 6, [1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 1])
        # 좌측 하단 파인더 패턴 위와 우측 상단 파인더 패턴 왼쪽에 버전 정보 추가
        bits_idx = 17
        for i in range(0, 6):
            for j in range(self.module_count - 11, self.module_count - 8):
                modules[j][i] = int(version_bits[bits_idx])
                modules[i][j] = int(version_bits[bits_idx])
                bits_idx -= 1

    def __add_format_information__(self, modules, mask_bit):
        '''
        포맷 정보를 추가하는 함수
        :param modules: qr코드 2darray
        :param mask_bit: 마스크 비트
        :return: 포맷 정보 추가가 완료된 qr코드 2darray
        '''
        # ecc level 비트 + 마스크 비트 = 포맷 비트
        format_bit = constants.ERROR_LEVEL_BITS[self.ecc_level] + mask_bit
        # 포맷 비트에 에러 정정 비트 추가
        format_bit += bch.bch_encode(int(format_bit, 2), 15, 5, [1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1])
        format_bit = [int(b) for b in format_bit]
        # 포맷 비트에 XOR 연산으로 마스크 적용
        mask = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0]
        for i in range(15):
            format_bit[i] = format_bit[i] ^ mask[i]

        # 지정된 위치에 포맷 정보 비트 추가
        bit_idx = 14
        # 좌측 상단 파인더 패턴 왼쪽
        for i in range(0, 9):
            if i == 6: continue
            modules[i][8] = format_bit[bit_idx]
            bit_idx -= 1
        # 좌측 상단 파인더 패턴 아래
        for i in range(7, -1, -1):
            if i == 6: continue
            modules[8][i] = format_bit[bit_idx]
            bit_idx -= 1

        bit_idx = 14
        # 우측 상단 파인더 패턴 아래
        for i in range(self.module_count - 1, self.module_count - 9, -1):
            if i == self.module_count - 8:
                modules[8][i] = 1
                continue
            modules[8][i] = format_bit[bit_idx]
            bit_idx -= 1
        # 좌측 하단 파인더 패턴 왼쪽
        for i in range(self.module_count - 8, self.module_count):
            modules[i][8] = format_bit[bit_idx]
            bit_idx -= 1
        return modules

    def __add_data_with_mask__(self, modules, mask_func):
        '''
        데이터를 마스킹 해서 추가하는 함수
        :param modules: qr코드 2darray
        :param mask_func: 마스크 적용 위치 판별 함수
        :return: 데이터 및 마스킹이 완료된 qr코드 2darray
        '''

        # 세로 이동 방향
        direction_y = -1
        # qr코드 가로 위치
        x = self.module_count - 1
        # qr코드 세로 위치
        y = self.module_count - 1

        # 비트 idx 0~7
        bit_idx = 0
        # 바이트(블록) idx
        byte_idx = 0

        # 모든 칸을 순회
        while True:
            # 아무 데이터도 없는 칸이라면
            if modules[y][x] == 2:
                # 데이터 비트 0으로 초기화
                target_bit = 0
                # 아직 블록이 남았다면
                if byte_idx < len(self.data_block):
                    # 블록의 bit_idx번째 비트 가져오기
                    target_bit = int(self.data_block[byte_idx][bit_idx])

                # 마스크를 적용시킬 칸 이라면 비트 반전
                if mask_func(y, x):
                    target_bit ^= 1
                # qr코드에 비트 적용
                modules[y][x] = target_bit
                # 비트 idx + 1
                bit_idx += 1
                # 8비트 모두 사용했다면 다음 블록으로 넘어가기
                if bit_idx == 8:
                    bit_idx = 0
                    byte_idx += 1

            # 데이터가 들어갈 수 있는 마지막 칸에 도달하면 break
            if x == 0 and y == self.module_count - 9:
                break

            # 규칙에 따라 칸을 순회하도록 설정
            if (x % 2 == 0) ^ (x <= 6):
                x -= 1
            else:
                x += 1
                y += direction_y
                if y < 0:
                    direction_y = 1
                    y = 0
                    x -= 2
                elif y >= self.module_count:
                    direction_y = -1
                    y = self.module_count - 1
                    x -= 2
            if x == 6:
                x -= 1

        return modules

    def __make__(self):
        self.__encode_data__()
        self.__add_error_bits__()

        # 버전 정보로 qr코드에 들어가는 비트 개수 산출
        self.module_count = self.version * 4 + 17
        # qr코드를 표현할 2darray
        modules = [[2] * self.module_count for _ in range(self.module_count)]
        # 좌측 상단 파이더 패턴 추가
        self.__add_finder_pattern__(modules, 0, 0)
        # 우측 상단 파인더 패턴 추가
        self.__add_finder_pattern__(modules, self.module_count - 7, 0)
        # 좌측 하단 파인더 패턴 추가
        self.__add_finder_pattern__(modules, 0, self.module_count - 7)
        # 정렬 패턴 추가
        self.__add_align_pattern__(modules)
        # 타이밍 패턴 추가
        self.__add_timing_pattern__(modules)

        # qr코드의 버전이 7 이상이면 버전 정보 추가
        if self.version >= 7:
            self.__add_version_information__(modules)

        # 가장 낮은 패널티 점수
        min_penalty = 1e10
        # 가장 낮은 패널티의 마스크 비트
        min_mask = 0
        # 가장 낮은 패널티의 qr코드
        min_module = []
        # 모든 마스크 비트 생성
        for mask_bit in constants.MASK_BITS:
            # 마스크에 따라 마스크 함수 가져오기
            mask_f = constants.MASK_FUNCTION[mask_bit]
            # 현재 qr코드 deepcopy
            option = copy.deepcopy(modules)
            # ecc level, 마스크 정보를 포함한 포맷 정보 추가
            option = self.__add_format_information__(option, mask_bit)
            # 마스크를 적용해서 데이터 영역 추가
            option = self.__add_data_with_mask__(option, mask_f)
            # 마스크 적용 패널티 계산
            penalty = util.evaluate_mask(option, self.module_count)
            # 패널티 점수가 가장 작다면 해당 버전의 qr코드 저장
            if penalty < min_penalty:
                min_penalty = penalty
                min_module = option
                min_mask = mask_bit
        # 최종 qr코드 데이터 확정
        self.qr_data = min_module
        
    def save_image(self, dir):
        width, height = 4 * self.module_count, 4 * self.module_count
        image = Image.new('1', (32 + width, 32 + height))
        pixels = image.load()

        for i in range(32 + width):
            for j in range(32 + height):
                pixels[i, j] = 1

        for i in range(self.module_count):
            for j in range(self.module_count):
                for p_i in range(i * 4 + 16, i * 4 + 20):
                    for p_j in range(j * 4 + 16, j * 4 + 20):
                        pixels[p_j, p_i] = 1 - self.qr_data[i][j]
        image.save(dir)
