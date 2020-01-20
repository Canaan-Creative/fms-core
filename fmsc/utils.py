# -*- coding: utf-8; -*-
# Copyright 2020-2021 Canaan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import datetime
import math
import time
import typing


def firmware_date_str(ver):
    if not ver:
        return ver
    parts = ver.strip().split('-')
    if len(parts[0]) == 7:  # A9 and before have ver like 9211809-b150820
        return parts[0][3:] if ver[3].isdigit() else parts[0][4:]
    else:   # A10 like 1066-xx-19111502_e1a9ab6_6d08130
        ver_parts_without_miner_type = parts[-1].split('_')
        if len(ver_parts_without_miner_type) >= 3:
            return ver_parts_without_miner_type[0]
        else:
            return ver


def has_any_none_in_iterable(iterable_v):
    for v in iterable_v:
        if v is None:
            return True
    return False


def long_to_bytes(val, expect_byte_count=None, endianness='big'):
    # noinspection SpellCheckingInspection
    """
        Use :ref:`string formatting` and :func:`~binascii.unhexlify` to
        convert ``val``, a :func:`long`, to a byte :func:`str`.

        :param expect_byte_count:
        :param long val: The value to pack

        :param str endianness: The endianness of the result. ``'big'`` for
          big-endian, ``'little'`` for little-endian.

        If you want byte- and word-ordering to differ, you're on your own.

        Using :ref:`string formatting` lets us use Python's C innards.
        """
    from binascii import unhexlify
    # one (1) hex digit per four (4) bits
    width = val.bit_length()

    # unhexlify wants an even multiple of eight (8) bits, but we don't
    # want more digits than we need (hence the ternary-ish 'or')
    width += 8 - ((width % 8) or 8)
    if expect_byte_count is not None and expect_byte_count > width // 8:
        width = expect_byte_count * 8

    # format width specifier: four (4) bits per hex digit
    fmt = '%%0%dx' % (width // 4)

    # prepend zero (0) to the width, to zero-pad the output
    s = unhexlify(fmt % val)

    if endianness == 'little':
        # see http://stackoverflow.com/a/931095/309233
        s = s[::-1]

    return s


def measurable_time():
    return time.monotonic()


def now_exact_str():
    return str(datetime.datetime.now())


def parse_cgminer_bracket_format_str(bs):
    """
    this only parse to str:str pair, it will not break down value str.
    If needed, please ref parse_cgminer_bracket_format_str_into_json
    """
    import re
    result = {}
    items = re.findall(r"\s*([^ \[\]]+)\[([^\[\]]+)\]\s*", bs)
    for item in items:
        if len(item) >= 2:
            result[item[0]] = item[1]
    return result


def parse_cgminer_bracket_format_str_into_json(bs):
    r = parse_cgminer_bracket_format_str(bs)
    new_values = {}
    for k, v in r.items():
        striped_v = v.strip()  # type: str
        items = striped_v.split()
        if len(items) == 1:
            float_v = str2float(striped_v, default=None)
            if float_v is not None and not math.isinf(float_v):
                int_v = int(float_v)
                new_values[k] = float_v if int_v != float_v else int_v
        else:
            float_items = [str2float(item) for item in items]
            if not has_any_none_in_iterable(float_items):
                int_items = [int(fv) for fv in float_items if fv is not None and not math.isinf(fv) and int(fv) == fv]
                new_values[k] = int_items if len(int_items) == len(float_items) else float_items
    r.update(new_values)
    return r


def random_str_only_with_alnum(n=6):
    import random
    import string
    return ''.join([random.SystemRandom().choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
                    for _ in range(n)])


def str2primitive(s, t, default):
    try:
        return t(s)
    except Exception:
        return default


def str2int(s, default: typing.Optional[int] = 0):
    return str2primitive(s, int, default)


def str2float(s, default: typing.Optional[float] = 0.0):
    if isinstance(s, str):
        tmp_s = s.strip()
        if tmp_s.endswith('%'):
            scale = 0.01
            tmp_s = tmp_s[:-1]
            f = str2primitive(tmp_s, float, default)
            if isinstance(f, float):
                f = f * scale
            return f
        else:
            return str2primitive(tmp_s, float, default)
    else:
        return str2primitive(s, float, default)


def str2bool(s, default: typing.Optional[bool] = False):
    if s is None:
        return default
    f = str2float(s, None)
    if f is not None:
        return f > 0
    return str(s) in ('true', 'True', 'TRUE', '1', 't', 'T',
                      'y', 'Y', 'yes', 'Yes', 'YES', 'yeah', 'yup',
                      'certainly', 'uh-huh')


def to_str(bytes_or_str):
    if isinstance(bytes_or_str, str):
        return bytes_or_str
    elif isinstance(bytes_or_str, bytes):
        return bytes_or_str.decode('utf-8')
    else:
        return str(bytes_or_str)


def to_bytes(bytes_or_str):
    if isinstance(bytes_or_str, str):
        return bytes_or_str.encode('utf-8')
    elif isinstance(bytes_or_str, bytes):
        return bytes_or_str
    else:
        str_value = str(bytes_or_str)
        return str_value.encode('utf-8')


class VirtualListAdder(object):
    def __init__(self,
                 list1,
                 list1_start_idx: typing.Optional[int] = None,
                 list1_range_len: typing.Optional[int] = None,
                 list2=None,
                 list2_start_idx: typing.Optional[int] = None,
                 list2_range_len: typing.Optional[int] = None):
        self.list1 = list1 if list1 is not None else []
        self.list1_start_idx = list1_start_idx if list1_start_idx is not None else 0
        self.list1_range_len = list1_range_len \
            if list1_range_len is not None else len(self.list1) - self.list1_start_idx
        self.list2 = list2 if list2 is not None else self.list1[0:0]
        self.list2_start_idx = list2_start_idx if list2_start_idx is not None else 0
        self.list2_range_len = list2_range_len \
            if list2_range_len is not None else len(self.list2) - self.list2_start_idx

    def __len__(self):
        return self.list1_range_len + self.list2_range_len

    def __getitem__(self, item):
        if isinstance(item, slice):
            start, stop, step = item.indices(len(self))
            if not((start >= stop) ^ (step > 0)):
                return self.empty()
            return (self.range_values(start, stop - start)[::step]
                    if stop >= start
                    else self.range_values(stop + 1, start - stop)[::step])
        elif isinstance(item, int):
            r = self.range_values(item, 1)
            return r[0] if len(r) > 0 else self.empty()
        else:
            raise TypeError('Index must be int or slice, not {}'.format(type(item).__name__))

    def empty(self):
        return self.list1[0:0]

    def range_values(self, start_idx, count):
        if start_idx + count <= self.list1_range_len:
            header_cur_idx = start_idx + self.list1_start_idx
            result = self.list1[header_cur_idx:(header_cur_idx + count)]
            return result
        elif start_idx < self.list1_range_len:  # should compose
            header_cur_idx = start_idx + self.list1_start_idx
            result = self.list1[header_cur_idx:(self.list1_start_idx + self.list1_range_len)]
            len_in_img = count - (self.list1_range_len - start_idx)
            end_idx = min(self.list2_start_idx + len_in_img, self.list2_start_idx + self.list2_range_len)
            result += self.list2[self.list2_start_idx:end_idx]
            return result
        else:
            img_start_idx = self.list2_start_idx + start_idx - self.list1_range_len
            end_idx = min(img_start_idx + count, self.list2_start_idx + self.list2_range_len)
            result = self.list2[img_start_idx:end_idx]
            return result
