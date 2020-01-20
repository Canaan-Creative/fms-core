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

import binascii
import os
import struct
from io import BufferedIOBase
from struct import Struct
from . import utils as uf
from .aupparser import AupHeader
import logging

_logger = logging.getLogger(__file__)


class AUPHeaderInfo(object):
    def __init__(self, aup_file):
        """
        init from file path or binary payload or io
        :param aup_file:
        """
        self._err_msg_list = []
        self._is_legal = False
        self.parsed_header = None
        try:
            if isinstance(aup_file, str):
                is_file_path = False
                try:
                    is_file_path = os.path.isfile(aup_file)
                except Exception:
                    pass
                if is_file_path:
                    self.parsed_header = AupHeader.from_file(aup_file)
                else:
                    self.parsed_header = AupHeader.from_bytes(aup_file)
            elif isinstance(aup_file, bytes):
                self.parsed_header = AupHeader.from_bytes(aup_file)
            elif isinstance(aup_file, BufferedIOBase):
                self.parsed_header = AupHeader.from_io(aup_file)
            else:
                raise RuntimeError("Illegal parameter for AUPHeaderInfo")
            if self.parsed_header is None:
                raise RuntimeError("AUP header parser init failed")
        except Exception as e:
            _logger.exception("AUPHeaderInfo init end with exception")
            self._is_legal = False
            self._err_msg_list.append("%s: %s" % (repr(e), str(e)))
            return

        self._supported_hwtype_list = []
        try:
            if self.magic() != 'AUP format':
                self._err_msg_list.append("illegal AUP file")
                return
            fmt_ver = self.parsed_header.fmt_ver
            if fmt_ver is None:
                self._err_msg_list.append("AUP file illegal: fmt ver")
                return
            target_ver = self.firmware_ver()
            self._hack_supported_hwtype_list(target_ver)
            if fmt_ver in (1,):
                self._supported_hwtype_list += [
                    uf.to_str(hwtype_str).strip('\0').strip()
                    for hwtype_str in self.parsed_header.header_data.hw_list.hw_str_list]
            if fmt_ver in (2,):
                self._supported_hwtype_list += [
                    uf.to_str(hw_item.str_value).strip('\0').strip()
                    for hw_item in self.parsed_header.header_data.hw_list]
            self._is_legal = True
        except Exception as _:
            self._err_msg_list.append("analyse_aup_file get exception")
            _logger.exception(self.err_message())

    def _hack_supported_hwtype_list(self, target_ver):
        # noinspection SpellCheckingInspection
        if target_ver in (
                '19092001_01ce5cf_789e6f2',
                '19101401_956c147_08bcf10',
                '19101201_fe411a8_71edeca',
                '19101501_f293f38_2fbfeda',
        ):
            self._supported_hwtype_list.append('MM3v1_X3')

    def is_legal(self):
        """
        whether init success and read all necessary fields value correctly
        :return:
        """
        return self._is_legal

    def all_supported_hwtype_list(self):
        return self._supported_hwtype_list

    def err_message(self):
        return ','.join(self._err_msg_list)

    def firmware_ver(self):
        return uf.to_str(self.parsed_header.header_data.firmware_ver).strip('\0').strip()

    def aup_header_ver(self):
        return self.parsed_header.fmt_ver

    def all_supported_swtype_list(self):
        if self.is_legal() and hasattr(self.parsed_header.header_data, 'sw_list'):
            return [uf.to_str(sw_item.str_value).strip('\0').strip()
                    for sw_item in self.parsed_header.header_data.sw_list]
        return []

    def total_len(self):
        aup_ver = self.aup_header_ver()
        if aup_ver == 0:
            return 92
        elif aup_ver == 1:
            return 224
        elif aup_ver == 2:
            return (100
                    + 32*(self.parsed_header.header_data.hw_list_count + self.parsed_header.header_data.sw_list_count)
                    + 4)

    def magic(self):
        return uf.to_str(self.parsed_header.magic).strip('\0').strip()

    def payload_len(self):
        return self.parsed_header.header_data.payload_len

    def payload_crc(self):
        return self.parsed_header.header_data.payload_crc

    def hw_list_count(self):
        return len(self._supported_hwtype_list)

    def sw_list_count(self):
        if self.is_legal() and hasattr(self.parsed_header.header_data, 'sw_list'):
            return len(self.parsed_header.header_data.sw_list)
        return 0


class AUPFile(object):
    def __init__(self, file_path):
        self.file_path = file_path
        with open(self.file_path, 'rb') as f:
            self.raw_payload = f.read()
        self.header_info = AUPHeaderInfo(self.raw_payload)

    def header(self):
        return self.header_info

    def is_1066(self):
        for hwtype in self.header_info.all_supported_hwtype_list():
            if hwtype.startswith('MM3v1_X3'):
                return True
        return False

    def file_content_binary(self):
        return self.raw_payload

    def aup_header_binary(self):
        return self.raw_payload[:self.header_info.total_len()]

    def generate_aup_header_payload(self, target_aup_ver):
        """
        return (fake header binary, original binary, payload start idx in original binary
        :param target_aup_ver:
        :return:
        """
        if not self.header_info.is_legal():
            return self.aup_header_binary()
        if target_aup_ver == self.header_info.aup_header_ver():
            return self.aup_header_binary()
        if target_aup_ver == 0:
            aup0_header_struct = Struct('<16sII64sI')
            aup0_header_binary = aup0_header_struct.pack(
                uf.to_bytes(self.header_info.magic()),
                target_aup_ver,
                self.header_info.payload_len(),
                uf.to_bytes(self.header_info.firmware_ver()),
                self.header_info.payload_crc())
            return aup0_header_binary
        elif target_aup_ver == 2:
            hw_list = self.header_info.all_supported_hwtype_list()
            if len(hw_list) == 0:
                hw_list.append('MM3v1_X3')
            sw_list = self.header_info.all_supported_swtype_list()
            if len(sw_list) == 0:
                sw_list.append('MM310')
            fixed_list_item_len = 32
            aup2_header_struct_before_crc = Struct('<16sII64sIII%ss%ss' % (
                len(hw_list) * fixed_list_item_len, len(sw_list) * fixed_list_item_len))
            aup2_header_before_crc = aup2_header_struct_before_crc.pack(
                uf.to_bytes(self.header_info.magic()),
                target_aup_ver,
                self.header_info.payload_len(),
                uf.to_bytes(self.header_info.firmware_ver()),
                self.header_info.payload_crc(),
                len(hw_list),
                len(sw_list),
                uf.to_bytes(''.join([hw.ljust(fixed_list_item_len, '\x00') for hw in hw_list])),
                uf.to_bytes(''.join([sw.ljust(fixed_list_item_len, '\x00') for sw in sw_list])))
            aup2_header_crc = struct.pack('<I', (binascii.crc32(aup2_header_before_crc) & 0xffffffff))
            aup2_header_binary = aup2_header_before_crc + aup2_header_crc
            return aup2_header_binary
        else:
            return self.aup_header_binary()
