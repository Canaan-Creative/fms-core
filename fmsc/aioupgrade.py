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

import asyncio
import re
import traceback
from enum import Enum
import time
import logging

import typing

from . import utils as uf
from .cgminerapi import CGMinerAPI, CGMinerStatus, CGMinerStatusCode, UpgradeErrCode


_logger = logging.getLogger(__file__)

kUpgradeErrRe = re.compile(r".*\s+Err(\d+):")

# offset error response looks like: Err04: offset(a68) is not expected(0)
kUpgradeErrUnexpectedOffsetRe = re.compile(
    r".*\s+Err(\d+):\s*offset\s+\(([0-9a-z]+)\)\s+is\s+not\s+expected\s+\(([0-9a-z]+)\)")


class UpgradeResults(Enum):
    success = 0,
    already_upgraded = 1,
    no_prev_ver = -1,
    reboot_timeout = -2,
    upgrade_timeout = -3,
    unexpected_error = -4,
    unexpected_final_ver = -5,
    out_of_memory = -6,
    mismatch_hwtype = -7,
    mismatch_swtype = -8,
    cancelled = -9,
    api_ver_mismatch = -10,
    invalid_header = -11,
    file_size_mismatch = -12,
    payload = -13,
    aup = -14,

    @classmethod
    def from_upgrade_err_code(cls, err_code: UpgradeErrCode):
        if err_code == UpgradeErrCode.UPGRADE_ERR_APIVER:
            return cls.api_ver_mismatch
        elif err_code == UpgradeErrCode.UPGRADE_ERR_HEADER:
            return cls.invalid_header
        elif err_code == UpgradeErrCode.UPGRADE_ERR_FILESIZE:
            return cls.file_size_mismatch
        elif err_code == UpgradeErrCode.UPGRADE_ERR_PAYLOAD:
            return cls.payload
        elif err_code == UpgradeErrCode.UPGRADE_ERR_MALLOC:
            return cls.out_of_memory
        elif err_code == UpgradeErrCode.UPGRADE_ERR_HARDWARE:
            return cls.mismatch_hwtype
        elif err_code == UpgradeErrCode.UPGRADE_ERR_AUP:
            return cls.aup
        else:
            return cls.unexpected_error


upgrade_result_display = {
    UpgradeResults.success: "upgrade success",
    UpgradeResults.already_upgraded: "already upgraded, no new upgrade",
    UpgradeResults.no_prev_ver: "get prev ver failed",
    UpgradeResults.reboot_timeout: "timeout when reboot after upgrade",
    UpgradeResults.upgrade_timeout: "timeout when upgrade",
    UpgradeResults.unexpected_error: "unexpected error occur",
    UpgradeResults.unexpected_final_ver: "unexpected final ver",
    UpgradeResults.out_of_memory: "out of memory",
    UpgradeResults.mismatch_hwtype: "hardware mismatch",
    UpgradeResults.mismatch_swtype: "software mismatch",
    UpgradeResults.cancelled: "cancelled",
    UpgradeResults.api_ver_mismatch: "API ver mismatch",
    UpgradeResults.invalid_header: "invalid header",
    UpgradeResults.file_size_mismatch: "file size mismatch",
    UpgradeResults.payload: "payload",
    UpgradeResults.aup: "aup",
}


class UpgradeStatus(Enum):
    Prepare = 'prepare',
    PreCheckVer = 'pre_check_ver',
    TransferFirmware = 'transfer_firmware',
    Reboot = 'reboot',
    PostCheckVer = 'post_check_ver',
    Finish = 'finish',


class UpgradeProgressInfo(typing.NamedTuple):
    ip: str
    port: int
    ratio: float
    status: UpgradeStatus
    result: typing.Optional[UpgradeResults] = None


async def aio_mm3_upgrade(
        ip, port, api_version, version, payload,
        page_len=888,
        timeout=10 * 60,
        enable_pre_ver_check=True,
        progress_report_fxn: typing.Callable[
            [typing.Union[float, UpgradeResults], UpgradeStatus], typing.NoReturn] = None,
        supported_hwtype_list=None,
        supported_swtype_list=None,
        aup_file=None):
    upgrade_result = UpgradeResults.unexpected_error
    try:
        _logger.info(f"upgrade start. ip {ip}")
        max_get_ver_seconds = 5*60
        if progress_report_fxn:
            progress_report_fxn(0, UpgradeStatus.PreCheckVer)
        pre_check_tuple = await aio_mm3_upgrade_pre_check(
            enable_pre_ver_check, ip, port,
            version, max_get_ver_seconds,
            supported_hwtype_list, supported_swtype_list)
        pre_check_err, pre_check_result, prev_ver, prev_when, upgrade_api_ver = pre_check_tuple
        if pre_check_result is not None:
            upgrade_result = pre_check_err
            return pre_check_result, upgrade_result
        if api_version <= 0:
            api_version = upgrade_api_ver
        if api_version < 2:
            payload = payload[aup_file.header().total_len() if aup_file.header().is_legal() else 92:]
        else:
            payload = _hack_aup_header_when_cross_aup_header_ver_upgrade(payload, aup_file, prev_ver)

        # distribute payload/firmware
        file_size = len(payload)
        reboot_progress_ratio = 0.1
        pre_check_progress_ratio = (1 - reboot_progress_ratio) * page_len / file_size
        upgrade_progress_ratio = 1 - pre_check_progress_ratio - reboot_progress_ratio
        offset = 0
        start_time = time.time()
        uid = int(start_time)
        timeout_error = False
        payload_len = 0
        if progress_report_fxn:
            progress_report_fxn(pre_check_progress_ratio, UpgradeStatus.TransferFirmware)
        while offset < file_size:
            success = False
            repeat_times_for_same_offset = 0
            should_reset_offset_to = None
            while not success:
                end_pos = min(offset + page_len, file_size)
                payload_len = end_pos - offset
                payload_part = payload[offset: end_pos]
                result = None
                try:
                    _logger.debug(
                        f"api call at {uf.now_exact_str()} {time.time() - start_time:6.1f} ip: {ip} port: {port}")
                    result = await CGMinerAPI.aio_mm3_upgrade(ip, uid, api_version, version, file_size,
                                                              offset, payload_len, payload_part, port,
                                                              10 if end_pos != file_size else 90)
                    if result and result.status_code() == CGMinerStatusCode.Cancelled:
                        raise asyncio.CancelledError()
                    if result.result:
                        prev_when = uf.str2int(result.when(), default=prev_when)
                    _logger.debug(f"{ip} upgrade package result: {result.debug_str()}")
                    success = result.is_request_success()
                except asyncio.CancelledError:
                    _logger.debug(f"ip {ip} port {port} cancelled")
                    raise
                except Exception as retry_e:
                    _logger.exception(f"ip {ip} port {port} exception {retry_e}")
                if not success and time.time() > start_time + timeout:
                    _logger.debug(f"{ip}:{port} upgrade timeout: from {start_time} to {time.time()}")
                    timeout_error = True
                    break
                elif result and result.status() == CGMinerStatus.Error:
                    if result.status_code() == CGMinerStatusCode.AscsetErr:
                        msg = result.status_msg()
                        err_matched = kUpgradeErrRe.match(msg)
                        if err_matched:
                            err_code = uf.str2int(err_matched.group(1))
                            if err_code == UpgradeErrCode.UPGRADE_ERR_OFFSET:
                                err_matched = kUpgradeErrUnexpectedOffsetRe.match(msg)
                                if err_matched:
                                    expected_offset_str = err_matched.group(2)
                                    should_reset_offset_to = uf.str2int(expected_offset_str)
                                else:
                                    should_reset_offset_to = 0
                                break
                            else:
                                result_enum = UpgradeResults.from_upgrade_err_code(err_code)
                                _logger.error(f"upgrade result: err code {err_code} {result_enum!r}. ip {ip}:{port}")
                                upgrade_result = result_enum
                                return False, upgrade_result
                    repeat_times_for_same_offset += 1
                    _logger.debug("repeat for error. repeat_times_for_same_offset %s at %s:%s" % (
                        repeat_times_for_same_offset, ip, port))
                    min_page_len = 500
                    # Right now we ignore "Invalid JSON" error and repeat until timeout
                    if result.status_code() == CGMinerStatusCode.InvalidJson:
                        if page_len > min_page_len and repeat_times_for_same_offset % 3 == 2:
                            page_len = max(page_len - 50, page_len//2, min_page_len)
                    else:
                        _logger.info(f"cgminer api error: ip: {ip}, result: {result.response_str()}")
            offset += payload_len
            if should_reset_offset_to is not None:
                _logger.error(f"offset reset from {offset} to {should_reset_offset_to} for {ip}:{port}")
                offset = should_reset_offset_to
                if should_reset_offset_to == 0:
                    old_uid = uid
                    uid = int(time.time())
                    _logger.info(f"{ip}:{port} uid changed from {old_uid} to {uid}")
            if progress_report_fxn:
                progress_report_fxn(pre_check_progress_ratio + upgrade_progress_ratio * offset / file_size,
                                    UpgradeStatus.TransferFirmware)
            if time.time() > start_time + timeout:
                timeout_error = True
                break
        _logger.info(f"upgrade finish ip: {ip}:{port} ds: {time.time() - start_time:6.1f}")
        if not timeout_error:
            if progress_report_fxn:
                progress_report_fxn(pre_check_progress_ratio + upgrade_progress_ratio, UpgradeStatus.Reboot)
            _logger.info(f"begin reboot ip: {ip}:{port} ds: {time.time() - start_time:6.1f}")
            start_ts = time.time()
            max_allowed_when_reboot_seconds = 5 * 60
            max_allowed_zero_reboot_seconds = 1 * 60
            max_allowed_reboot_seconds = max_allowed_when_reboot_seconds + max_allowed_zero_reboot_seconds
            new_ver, new_when, upgrade_api_ver = None, None, 1
            reboot_when = max(prev_when, 15)
            reboot_success = False
            max_get_ver_seconds_after_reboot = max_get_ver_seconds
            ts_before_start_reboot = time.time()
            while True:
                _logger.debug(f"reboot ip: {ip}:{port} ds: {time.time() - start_time:6.1f}")
                error_info = []
                reboot_result = await CGMinerAPI.aio_reboot_mm3(
                    ip, last_when=reboot_when, port=port, error_info=error_info)
                if reboot_result and reboot_result.status_code() == CGMinerStatusCode.Cancelled:
                    raise asyncio.CancelledError()
                if len(error_info) > 0:
                    _logger.debug(f"reboot {ip}:{port} error info: {error_info}")
                    if (reboot_when == 0
                            and reboot_result is not None
                            and not reboot_result.result):
                        latest_err_info = error_info[-1]
                        if latest_err_info.get('timeout') and latest_err_info.get('connect_success'):
                            _logger.debug("timeout is acceptable for MM3 firmware right now")
                            # if reboot with 0, it always timeout
                            # and we should wait for enough time before it become responsible
                            # however, we still verify that when become less than prev when
                            max_allowed_restart_seconds = 3*60
                            _, tmp_when, _, _, _ = await _aio_get_ver_when_and_upgrade_api(
                                ip, max_allowed_restart_seconds, port)
                            if tmp_when and tmp_when < prev_when + (time.time() - ts_before_start_reboot):
                                max_get_ver_seconds_after_reboot = 60
                                reboot_success = True
                                break
                if (reboot_result is not None
                        and reboot_result.result
                        and not reboot_result.is_request_success()
                        and (reboot_result.status_msg().find('Wrong parameter') >= 0
                             and reboot_result.when() < max(prev_when, 30))):
                    # if reboot get response and is error, it means "when" check failed, so means we success reboot
                    _logger.debug(
                        f"this reboot request failed with smaller when {prev_when}:{reboot_result.when()},"
                        f" so reboot success")
                    reboot_success = True
                    break
                _logger.info(f"reboot {ip}:{port} result: {reboot_result.debug_str() if reboot_result else None}")
                if progress_report_fxn:
                    progress_report_fxn(pre_check_progress_ratio + upgrade_progress_ratio, UpgradeStatus.Reboot)
                await asyncio.sleep(0.3)
                if time.time() > start_ts + max_allowed_reboot_seconds:
                    _logger.info("%s:%s reboot timeout from %s to %s" % (ip, port, start_ts, time.time()))
                    timeout_error = True
                    break
                elif time.time() > start_ts + max_allowed_when_reboot_seconds:
                    reboot_when = 0
            _logger.info(f"end reboot ip: {ip}:{port} ds: {time.time() - start_time:6.1f}")
            if timeout_error:
                _logger.info(f"upgrade result: failed. ip: {ip}:{port} failed for reboot timeout")
                upgrade_result = UpgradeResults.reboot_timeout
                return False, upgrade_result
            if reboot_success:
                if progress_report_fxn:
                    progress_report_fxn(pre_check_progress_ratio + upgrade_progress_ratio, UpgradeStatus.PostCheckVer)
                new_ver, new_when, upgrade_api_ver, _, _ = await _aio_get_ver_when_and_upgrade_api(
                    ip, max_get_ver_seconds_after_reboot, port)
            if new_ver and new_ver.startswith(version) and new_when and new_when < prev_when:
                _logger.debug(
                    f"upgrade result: success. ip: {ip}, prev ver: {prev_ver} prev when: {prev_when},"
                    f" new ver: {new_ver} new when {new_when}")
                upgrade_result = UpgradeResults.success
                return True, upgrade_result
            else:
                _logger.debug(
                    f"upgrade result: failed. ip: {ip}, prev ver: {prev_ver} prev when: {prev_when},"
                    f" target ver: {version}, new ver: {new_ver} new when {new_when}")
                upgrade_result = UpgradeResults.unexpected_final_ver
                return False, upgrade_result
        else:
            _logger.info(f"upgrade result: failed. ip: {ip}:{port} failed for timeout")
            upgrade_result = UpgradeResults.upgrade_timeout
            return False, upgrade_result
    except asyncio.CancelledError:
        _logger.info(f"upgrade result: cancelled. ip {ip}:{port}, stack: {traceback.format_exc()}")
        upgrade_result = UpgradeResults.cancelled
        return False, upgrade_result
    except Exception as mm3_upgrade_e:
        _logger.exception(f"upgrade result: failed. ip {ip}:{port} upgrade exception: {mm3_upgrade_e!r}")
        upgrade_result = UpgradeResults.unexpected_error
        return False, upgrade_result
    finally:
        _logger.info(f"upgrade end. ip {ip}:{port}")
        if progress_report_fxn:
            progress_report_fxn(upgrade_result, UpgradeStatus.Finish)


async def aio_mm3_upgrade_pre_check(enable_pre_ver_check, ip, port,
                                    target_version, max_get_ver_seconds,
                                    supported_hwtype_list,
                                    supported_swtype_list):
    pre_check_result = None
    pre_check_err = None
    # get current version and when first
    prev_ver, prev_when, upgrade_api_ver, hwtype, swtype = \
        await _aio_get_ver_when_and_upgrade_api(ip, max_get_ver_seconds, port)
    if prev_ver is None or len(prev_ver) == 0:
        if enable_pre_ver_check:
            pre_check_result = False
            pre_check_err = UpgradeResults.no_prev_ver
        else:
            _logger.warning("ip %s%s no prev ver" % (ip, port))
    elif prev_ver.startswith(target_version):
        _logger.warning("same ver at ip %s%s, no upgrade is needed" % (ip, port))
        pre_check_result = True
        pre_check_err = UpgradeResults.already_upgraded
    if supported_hwtype_list and len(supported_hwtype_list) > 0 and hwtype and hwtype not in supported_hwtype_list:
        _logger.warning("ver hwtype mismatch: cur ver %s, cur hwtype %s, target ver: %s, hwtype list %s" % (
            prev_ver, hwtype, target_version, supported_hwtype_list))
        pre_check_result = False
        pre_check_err = UpgradeResults.mismatch_hwtype
    if supported_swtype_list and len(supported_swtype_list) > 0 and swtype and swtype not in supported_swtype_list:
        _logger.warning("ver swtype mismatch: cur ver %s, cur swtype %s, target ver: %s, swtype list %s" % (
            prev_ver, swtype, target_version, supported_swtype_list))
        pre_check_result = False
        pre_check_err = UpgradeResults.mismatch_swtype
    return pre_check_err, pre_check_result, prev_ver, prev_when, upgrade_api_ver


async def _aio_get_ver_when_and_upgrade_api(ip, max_get_ver_seconds, port):
    timeout_error = False
    import time
    start_ts = time.time()
    prev_ver = None
    prev_when = None
    prev_upgrade_api_ver = 1
    hwtype = None
    swtype = None
    while True:
        if prev_ver is None:
            ver_result = await CGMinerAPI.aio_version(
                ip, port=port, first_timeout=max(10, min(max_get_ver_seconds, 60)))
            if ver_result and ver_result.status_code() == CGMinerStatusCode.Cancelled:
                raise asyncio.CancelledError()
            if ver_result.is_request_success():
                prev_ver = ver_result.mm3_software_version()
                prev_when = uf.str2int(ver_result.when(), default=60)
                prev_upgrade_api_ver = ver_result.mm3_upgrade_api_version()
                hwtype = ver_result.mm3_hardware_type()
                swtype = ver_result.mm3_software_type()
                break
        await asyncio.sleep(0.3)
        if time.time() > start_ts + max_get_ver_seconds:
            timeout_error = True
            break
    if timeout_error:
        _logger.error("ip: %s:%s failed for getting version timeout" % (ip, port))
    return prev_ver, prev_when, prev_upgrade_api_ver, hwtype, swtype


def _hack_aup_header_when_cross_aup_header_ver_upgrade(payload, aup_file, running_ver):
    if aup_file.is_1066():
        date_str = uf.firmware_date_str(running_ver)
        if date_str <= '19102501':
            use_aup_ver = 0
        else:
            use_aup_ver = 2
        if use_aup_ver is not None and use_aup_ver != aup_file.header().aup_header_ver():
            original_header_len = aup_file.header().total_len()
            return uf.VirtualListAdder(
                aup_file.generate_aup_header_payload(use_aup_ver),
                None, None,
                payload, original_header_len, None)
    return payload
