from PIL import Image
import copy
import re

import error_correction.reed_solomon as reed_solomon
import error_correction.bch as bch
import qrcode.constants as constants
import qrcode.util as util

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
        error_blocks = []
        error_block_size = constants.ERROR_BLOCK_TABLE[self.ecc_level][self.version - 1]
        for i in range(0, len(error_block_size), 4):
            block_count, total_count, data_count, error_count = error_block_size[i:i + 4]
            for idx in range(block_count):
                error_blocks.append((total_count, data_count, error_count))

        data_idx = 0
        data_code = []
        error_code = []

        max_data_length = 0
        max_error_data_length = 0
        # additional_blocks = 0
        for error_block in error_blocks:
            total_count, data_count, error_count = error_block
            error_count = total_count - data_count

            # additional_blocks += total_count - (data_count + 2 * error_count)

            max_data_length = max(max_data_length, data_count)
            max_error_data_length = max(max_error_data_length, error_count)

            target_data = []
            for idx in range(data_count):
                data = self.encoded_data[data_idx:data_idx + 8]
                target_data.append(data)
                data_idx += 8
            rs_data = reed_solomon.rs_encode_msg([int(d, 2) for d in target_data], error_count)
            rs_data = rs_data[len(target_data):]

            data_code.append(target_data)
            error_code.append([format(d, '08b') for d in rs_data])

        self.data_block = []
        for i in range(max_data_length):
            for d in data_code:
                if i < len(d):
                    self.data_block.append(d[i])
        for i in range(max_error_data_length):
            for d in error_code:
                if i < len(d):
                    self.data_block.append(d[i])
        # for _ in range(additional_blocks):
        #     self.data_block.append('00000000')

    def __encode_data__(self):
        self.mode = util.determine_mode(self.data)
        self.data_length = len(self.data)

        if self.mode == 'Byte':
            self.data = self.data.encode('utf-8')
            self.data_length = len(self.data)

        self.encoded_data = constants.MODE_BITS[self.mode]
        self.version = util.get_version(self.data_length, self.mode, self.ecc_level)
        char_count_indicator_length = util.get_char_count_indicator_length(self.version, self.mode)

        self.encoded_data += format(self.data_length, f'0{char_count_indicator_length}b')

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

        self.encoded_data = util.add_terminator_and_pad(
            self.encoded_data, constants.QRCODE_CAPACITY[self.ecc_level][self.version - 1])

    def __add_finder_pattern__(self, modules, start_x, start_y):
        for i in range(start_y - 1, start_y + 8):
            for j in range(start_x - 1, start_x + 8):
                if 0 <= i < self.module_count and 0 <= j < self.module_count:
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
                
    def __add_align_pattern__(self, modules):
        pos = constants.ALIGN_PATTERN_POSITION[self.version - 1]
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
        for i in range(8, self.module_count - 8):
            if modules[i][6] != 2: continue
            modules[i][6] = int(i % 2 == 0)
        for i in range(8, self.module_count - 8):
            if modules[6][i] != 2: continue
            modules[6][i] = int(i % 2 == 0)

    def __add_version_information__(self, modules):
        version_bits = format(self.version, '06b')
        version_bits += bch.bch_encode(self.version, 18, 6, [1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 1])
        bits_idx = 17
        for i in range(0, 6):
            for j in range(self.module_count - 11, self.module_count - 8):
                modules[j][i] = int(version_bits[bits_idx])
                modules[i][j] = int(version_bits[bits_idx])
                bits_idx -= 1

    def __add_format_information__(self, modules, mask_bit):
        format_bit = constants.ERROR_LEVEL_BITS[self.ecc_level] + mask_bit
        format_bit += bch.bch_encode(int(format_bit, 2), 15, 5, [1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1])
        format_bit = [int(b) for b in format_bit]
        mask = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0]
        for i in range(15):
            format_bit[i] = format_bit[i] ^ mask[i]

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
        for i in range(self.module_count - 1, self.module_count - 9, -1):
            if i == self.module_count - 8:
                modules[8][i] = 1
                continue
            modules[8][i] = format_bit[bit_idx]
            bit_idx -= 1
        for i in range(self.module_count - 8, self.module_count):
            modules[i][8] = format_bit[bit_idx]
            bit_idx -= 1
        return modules

    def __add_data_with_mask__(self, modules, mask_func):
        direction_y = -1
        x = self.module_count - 1
        y = self.module_count - 1

        bit_idx = 0
        byte_idx = 0
        while True:
            if modules[y][x] == 2:
                target_bit = 0
                if byte_idx < len(self.data_block):
                    target_bit = int(self.data_block[byte_idx][bit_idx])

                if mask_func(y, x):
                    target_bit ^= 1
                modules[y][x] = target_bit
                bit_idx += 1
                if bit_idx == 8:
                    bit_idx = 0
                    byte_idx += 1

            if x == 0 and y == self.module_count - 9:
                break

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

        self.module_count = self.version * 4 + 17
        modules = [[2] * self.module_count for _ in range(self.module_count)]
        self.__add_finder_pattern__(modules, 0, 0)
        self.__add_finder_pattern__(modules, self.module_count - 7, 0)
        self.__add_finder_pattern__(modules, 0, self.module_count - 7)
        self.__add_align_pattern__(modules)
        self.__add_timing_pattern__(modules)

        if self.version >= 7:
            self.__add_version_information__(modules)

        min_penalty = 1e10
        min_mask = 0
        min_module = []
        for mask_bit in constants.MASK_BITS:
            mask_f = constants.MASK_FUNCTION[mask_bit]
            option = copy.deepcopy(modules)
            option = self.__add_format_information__(option, mask_bit)
            option = self.__add_data_with_mask__(option, mask_f)
            penalty = util.evaluate_mask(option, self.module_count)
            if penalty < min_penalty:
                min_penalty = penalty
                min_module = option
                min_mask = mask_bit
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
