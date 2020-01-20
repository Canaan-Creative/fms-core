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

# -*- coding:utf-8 -*-

import asyncio
import errno
import json
import logging
import re
import socket
import time
import traceback
import typing
from enum import Enum, IntEnum

from . import utils as uf

_logger = logging.getLogger(__file__)

ERR_CODE_cancelled = 99999
kDefaultPort = 4028

supress_led_command_log = False


class CGMinerStatus(Enum):
    Warning = "W"
    Informational = "I"
    Success = "S"
    Error = "E"
    Fatal = "F"


class CGMinerStatusCode(IntEnum):
    Cancelled = 99999
    InvalidJson = 23
    AscsetErr = 120


class UpgradeErrCode(IntEnum):
    UPGRADE_ERR_APIVER = 1
    UPGRADE_ERR_HEADER = 2
    UPGRADE_ERR_FILESIZE = 3
    UPGRADE_ERR_OFFSET = 4
    UPGRADE_ERR_PAYLOAD = 5
    UPGRADE_ERR_MALLOC = 6
    UPGRADE_ERR_HARDWARE = 7
    UPGRADE_ERR_AUP = 8
    UPGRADE_ERR_UNKNOWN = 0xFF


class CGMinerAPIResult(object):
    KEY_STATUS = "STATUS"
    KEY_When = "When"
    KEY_Code = "Code"
    KEY_Msg = "Msg"
    KEY_Desc = "Description"

    def __init__(self, result, scan_timestamp, response, try_times, msg):
        """

        :param result:
        :param scan_timestamp:
        :param response: str or dict. If str, it should be json str. If dict, it should be loaded json result
        :param try_times:
        :param msg:
        """
        self.result = result  # bool. Whether API request receive data successfully. It doesn't mean API itself success.
        self.scan_timestamp = scan_timestamp  # unix timestamp. The time before request function is called

        if isinstance(response, bytes) or isinstance(response, bytearray):
            response = response.decode('utf-8', 'ignore')
        if isinstance(response, str):
            self.response = response  # json str. API raw response
            self._response_dict = None  # if loads json str once time, the result will be cached here
        else:
            self.response = json.dumps(response)  # json str
            self._response_dict = response  # dict of API result
        self.try_times = try_times  # int. real times the API has been called
        self.msg = msg  # str. error message

    @classmethod
    def error_result(cls, when, msg, code=14):
        response = {
            "STATUS": [{
                "STATUS": "E", "When": when,
                "Code": uf.str2int(code, default=14),
                "Msg": msg}],
            "id": 1
        }
        return CGMinerAPIResult(True, time.time(), response, 0, msg)

    def debug_str(self):  # for debug purpose only
        return "%s %s %s %s" % (
            self.result, self.scan_timestamp, self.response,
            self.msg if len(self.msg) < 300 else f"{self.msg[:150]} ... {self.msg[-150:]}")

    def response_dict(self):
        """
        loads response json str to convert it to dict.
        The caller should NOT change returned value.
        :return: dict. not None
        """
        if self._response_dict is not None:
            return self._response_dict
        if self.result and len(self.response) > 0:
            unicode_response = self.response
            try:
                self._response_dict = json.loads(unicode_response, strict=False)
            except Exception as e:
                sidx = 0
                eidx = 100
                peek_len = 50
                matched = re.compile(r'.*\(\s*char\s+(\d+)\s*-\s*(\d+)\s*\).*').match(str(e))
                if matched:
                    sidx = min(max(uf.str2int(matched.group(1)) - peek_len, 0), len(unicode_response))
                    eidx = min(max(uf.str2int(matched.group(2)) + peek_len, sidx), len(unicode_response))
                else:
                    matched = re.compile(r'.*\(\s*char\s+(\d+).*').match(str(e))
                    if matched:
                        sidx = min(max(uf.str2int(matched.group(1)) - peek_len, 0), len(unicode_response))
                        eidx = min(sidx + 2 * peek_len, len(unicode_response))
                _logger.exception(f"load api response failed. {sidx}:{eidx} <<<{unicode_response[sidx:eidx]}>>>")
        if self._response_dict is None:
            self._response_dict = {}
        return self._response_dict

    def response_str(self):
        return self.response

    def status_dict(self):
        rd = self.response_dict()
        if rd and self.KEY_STATUS in rd:
            status_array = rd[self.KEY_STATUS]
            if len(status_array) > 0:
                return status_array[0]
        return None

    def is_request_success(self):
        if self.result:
            status = self.status()
            return status == CGMinerStatus.Success or status == CGMinerStatus.Informational
        return False

    def status(self):
        status_dict = self.status_dict()
        if status_dict:
            try:
                return CGMinerStatus(status_dict[self.KEY_STATUS])
            except Exception:
                return CGMinerStatus.Fatal
        # if no status, it means that's a multiple reports command
        response_dict = self.response_dict()
        if isinstance(response_dict, dict) and len(response_dict) > 0:
            return CGMinerStatus.Success
        else:
            return CGMinerStatus.Fatal

    def when(self):
        status_dict = self.status_dict()
        if status_dict:
            return uf.str2float(status_dict.get(self.KEY_When), default=None)

    def status_msg(self):
        status_dict = self.status_dict()
        if status_dict:
            return status_dict.get(self.KEY_Msg)

    def status_code(self):
        status_dict = self.status_dict()
        if status_dict:
            return status_dict.get(self.KEY_Code)

    def success_response_dict(self, payload_key):
        if self.is_request_success():
            response_dict = self.response_dict()
            if payload_key in response_dict:
                return response_dict[payload_key]
        return None

    def stats(self):
        return self.success_response_dict("STATS")

    def summary(self):
        return self.success_response_dict("SUMMARY")

    def devs(self):
        return self.success_response_dict("DEVS")

    def pools(self):
        return self.success_response_dict("POOLS")

    def debug(self):
        # [{"Silent":true,"Quiet":false,"Verbose":false,"Debug":false,"RPCProto":false,"PerDevice":false,"WorkTime":false}]
        return self.success_response_dict("DEBUG")

    def minerupgrade(self):
        return self.success_response_dict("MINERUPGRADE")

    def version(self):
        return self.success_response_dict("VERSION")

    def mm3_software_version(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            if 'VERSION' not in version_list[0]:
                return version_list[0].get('VERION')  # firmware has a typo at 2019.5.17
            return version_list[0].get('VERSION')

    def mm3_upgrade_api_version(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            if 'UPAPI' not in version_list[0]:
                ver = self.mm3_software_version()
                if ver in ('19062002_1e9d1b0_61887c8', '19062001_d9eaa2c_c0487dd'):
                    return 2
                return 1
            return uf.str2int(version_list[0].get('UPAPI'), default=1)
        return 1

    def mm3_mac(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('MAC')

    def mm3_dna(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('DNA')

    def mm3_product_name(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('PROD')

    def mm3_model(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('MODEL')

    def mm3_hardware_type(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('HWTYPE')

    def mm3_software_type(self):
        version_list = self.version()
        if version_list is not None and len(version_list) > 0:
            return version_list[0].get('SWTYPE')


def request_cgminer_api_by_sock(
        ip, command, parameters,
        port=kDefaultPort,
        first_timeout=2,
        retry=0,
        use_json_command=True,
        error_info: typing.Optional[typing.List[typing.Union[str, dict]]] = None,
        auto_retry_if_refused_conn=True,
        total_timeout=30 * 60):
    """
    The response in return dict is a str, suggest to decode it as UTF-8
    """
    total_start_time = uf.measurable_time()
    if parameters is None:
        parameters = ''
    total_timeout_err = False
    try_times = 0
    buffer_len = 8 * 1024  # 8 KiB
    buffer_list = bytearray()
    err_msgs = []
    success = False
    scantime = time.time()
    unlimited_retry_count = 0
    api_request_id = uf.random_str_only_with_alnum()
    while not success and not total_timeout_err and try_times <= retry + unlimited_retry_count:
        if uf.measurable_time() > total_start_time + total_timeout:
            total_timeout_err = True
            err_msgs.append("total timeout")
            break
        start_time = time.time()
        if not supress_led_command_log or parameters.find(',led,') < 0:
            _logger.debug("[%s] [%s] [ip %s port %s] start command %s with parameter %s" % (
                api_request_id, uf.now_exact_str(), ip, port, command, parameters[:60]))
        sock = None
        timeout = float(try_times + first_timeout)  # seconds
        try_times += 1
        connect_success = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(min(timeout, max(0.1, start_time + total_timeout - time.time())))
            sock.connect((ip, int(port)))
            if uf.measurable_time() > total_start_time + total_timeout:
                total_timeout_err = True
                raise RuntimeError("total timeout")
            connect_success = True
            scantime = time.time()
            if use_json_command:
                cmd_json = json.dumps({"command": command, "parameter": parameters})
            else:
                cmd_json = "%s|%s" % (command, parameters)
            sock.settimeout(min(timeout, max(0.1, start_time + total_timeout - time.time())))
            sock.send(cmd_json.encode('latin1'))
            if uf.measurable_time() > total_start_time + total_timeout:
                total_timeout_err = True
                raise RuntimeError("total timeout")
            # _logger.debug("cmd_json", cmd_json)
            sock.settimeout(min(timeout, max(0.1, start_time + total_timeout - time.time())))
            received_data = sock.recv(buffer_len)
            while received_data:
                if uf.measurable_time() > total_start_time + total_timeout:
                    total_timeout_err = True
                    raise RuntimeError("total timeout")
                buffer_list.extend(received_data)
                sock.settimeout(min(timeout, max(0.1, start_time + total_timeout - time.time())))
                received_data = sock.recv(buffer_len)
            success = True
        except Exception as e:
            except_err = {}
            is_refuse_conn = False
            if error_info is not None:
                error_info.append(except_err)
            if isinstance(e, socket.timeout):
                except_err['timeout'] = True
                except_err['connect_success'] = connect_success
            if isinstance(e, socket.error) and e.errno is not None:
                except_err['socket_error_no'] = e.errno
                is_refuse_conn = e.errno == errno.ECONNREFUSED
                if is_refuse_conn and auto_retry_if_refused_conn:
                    unlimited_retry_count += 1
                    if error_info is not None and len(error_info) >= 2 \
                            and error_info[-2].get('socket_error_no') == errno.ECONNREFUSED:
                        del error_info[-1]
                    time.sleep(0.5)
            err_msgs.append(str(e))
            buffer_list = bytearray()
            if not isinstance(e, ConnectionRefusedError) \
                    and not isinstance(e, ConnectionResetError) and not is_refuse_conn:
                _logger.exception(
                    f"[{api_request_id}] [ip {ip} port {port}] "
                    f"exception when run command {command} with parameter {parameters[:60]}. "
                    f"err: {e}")
        finally:
            if sock:
                sock.close()
            dt = time.time() - start_time
            if not supress_led_command_log or parameters.find(',led,') < 0:
                _logger.debug(
                    f"[{api_request_id}] [ip {ip} port {port}] "
                    f"end command {command} with parameter {parameters[:60]}. dt: {dt}")
            if not success:
                time.sleep(0.1)
    response = None
    delta_total_time = uf.measurable_time() - total_start_time
    if success:
        response = buffer_list.rstrip(b'\x00')
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: success. command {command} with parameter {parameters[:60]}. dt: {delta_total_time}")
    elif total_timeout_err:
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: total timeout. "
            f"command {command} with parameter {parameters[:60]}."
            f" dt: {delta_total_time}")
        err_msgs.append("Total timeout. limit %s, real %s" % (total_timeout, delta_total_time))
    else:
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: other error."
            f"command {command} with parameter {parameters[:60]}."
            f" dt: {delta_total_time}. "
            f"err: {err_msgs[-1][:100] if err_msgs else 'no err msg'}")
    return CGMinerAPIResult(success, scantime, response, try_times, "\n".join(err_msgs))


async def aio_request_cgminer_api_by_sock(
        ip, command, parameters,
        port=kDefaultPort,
        first_timeout=2,
        retry=0,
        use_json_command=True,
        error_info=None,
        auto_retry_if_refused_conn=True,
        total_timeout=30 * 60,
        cancel_event: asyncio.Event = None):
    """
    The response in return dict is a str, suggest to decode it as UTF-8

    :param total_timeout:
    :param auto_retry_if_refused_conn:
    :param use_json_command:
    :param cancel_event:
    :type error_info: list
    :param ip:
    :param port:
    :param command:
    :param parameters:
    :param first_timeout: seconds
    :param retry:
    :return: CGMinerAPIResult
    """
    if cancel_event is not None and cancel_event.is_set():
        return canceled_result()
    total_start_time = uf.measurable_time()
    if parameters is None:
        parameters = ''
    total_timeout_err = False
    try_times = 0
    buffer_len = 8 * 1024  # 8 KiB
    buffer_list = bytearray()
    err_msgs = []
    success = False
    scantime = time.time()
    unlimited_retry_count = 0
    api_request_id = uf.random_str_only_with_alnum()
    cancel_task = asyncio.create_task(cancel_event.wait()) if cancel_event is not None else None
    cancelled = False
    while not success and not total_timeout_err and try_times <= retry + unlimited_retry_count:
        if uf.measurable_time() > total_start_time + total_timeout:
            total_timeout_err = True
            err_msgs.append("total timeout")
            break
        start_time = time.time()
        if not supress_led_command_log or parameters.find(',led,') < 0:
            _logger.debug("[%s] [%s] [ip %s port %s] start command %s with parameter %s" % (
                api_request_id, uf.now_exact_str(), ip, port, command, parameters[:60]))
        timeout = float(try_times + first_timeout)  # seconds
        try_times += 1
        connect_success = False
        remote_writer = None
        conn_task = None
        try:
            _logger.info(f"before conn {ip}")
            conn_task = asyncio.create_task(asyncio.open_connection(host=ip, port=uf.str2int(port, default=4028)))
            remote_reader, remote_writer = await wait_cancelable(
                conn_task,
                timeout=min(timeout, max(0.1, start_time + total_timeout - time.time())),
                cancel_task=cancel_task)
            _logger.info(f"after conn {ip}")
            connect_success = True
            scantime = time.time()
            if use_json_command:
                cmd_json = json.dumps({"command": command, "parameter": parameters})
            else:
                cmd_json = "%s|%s" % (command, parameters)
            remote_writer.write(cmd_json.encode('latin1'))
            write_task = asyncio.create_task(remote_writer.drain())
            await wait_cancelable(write_task,
                                  timeout=min(timeout, max(0.1, start_time + total_timeout - time.time())),
                                  cancel_task=cancel_task)
            if uf.measurable_time() > total_start_time + total_timeout:
                total_timeout_err = True
                raise RuntimeError("total timeout")
            # _logger.debug("cmd_json", cmd_json)
            read_task = asyncio.create_task(remote_reader.read(buffer_len))
            received_data = await wait_cancelable(
                read_task,
                timeout=min(timeout, max(0.1, start_time + total_timeout - time.time())),
                cancel_task=cancel_task)
            while received_data:
                if uf.measurable_time() > total_start_time + total_timeout:
                    total_timeout_err = True
                    raise RuntimeError("total timeout")
                buffer_list.extend(received_data)
                read_task = asyncio.create_task(remote_reader.read(buffer_len))
                received_data = await wait_cancelable(
                    read_task,
                    timeout=min(timeout, max(0.1, start_time + total_timeout - time.time())),
                    cancel_task=cancel_task)
            success = True
        except asyncio.CancelledError:
            cancelled = True
            _logger.info(f"cancel api {ip} {command} {parameters[:40]}, stack: {traceback.format_exc()}")
            return canceled_result()
        except asyncio.TimeoutError as e:
            except_err = {'timeout': True, 'connect_success': connect_success}
            if error_info is not None:
                error_info.append(except_err)
            err_msgs.append(f'{repr(e)}: {str(e)}')
            buffer_list = bytearray()
        except Exception as e:
            except_err = {}
            is_refuse_conn = False
            if error_info is not None:
                error_info.append(except_err)
            if isinstance(e, socket.timeout):
                except_err['timeout'] = True
                except_err['connect_success'] = connect_success
            if isinstance(e, socket.error) and e.errno is not None:
                except_err['socket_error_no'] = e.errno
                is_refuse_conn = e.errno == errno.ECONNREFUSED
                if is_refuse_conn and auto_retry_if_refused_conn:
                    unlimited_retry_count += 1
                    if error_info is not None and len(error_info) >= 2 \
                            and error_info[-2].get('socket_error_no') == errno.ECONNREFUSED:
                        del error_info[-1]
            if isinstance(e, ConnectionResetError):
                unlimited_retry_count += 1
            err_msgs.append(f'{repr(e)}: {str(e)}')
            buffer_list = bytearray()
            if not isinstance(e, ConnectionRefusedError) \
                    and not isinstance(e, ConnectionResetError) \
                    and not is_refuse_conn:
                _logger.exception(
                    f"[{api_request_id}] [ip {ip} port {port}] "
                    f"exception when run command {command} with parameter {parameters[:60]}. "
                    f"err: {e!r} {e}")
        finally:
            _logger.info(f"final conn {ip}")
            dt = time.time() - start_time
            if not supress_led_command_log or parameters.find(',led,') < 0:
                _logger.debug(f"[{api_request_id}] [{uf.now_exact_str()}] "
                              f"[ip {ip} port {port}] end command {command} with parameter {parameters[:60]}."
                              f" dt: {dt} error_info:{err_msgs[-1] if len(err_msgs) > 0 else ''}")
            try:
                if not remote_writer and conn_task:
                    if conn_task.done():
                        if not conn_task.exception() and not conn_task.cancelled():
                            _, remote_writer = conn_task.result()
                    elif not conn_task.cancelled():
                        conn_task.cancel()
                if remote_writer:
                    remote_writer.close()
                    await remote_writer.wait_closed()
                    _logger.info(f"conn closed {api_request_id} {ip}")
            except asyncio.CancelledError:
                _logger.info(f"cancel api {ip} {command} {parameters[:40]}, {traceback.format_exc()}")
                return canceled_result()
            except Exception as ee:
                if not isinstance(ee, ConnectionResetError):
                    _logger.info(
                        f"exception when wait writer closed {api_request_id} {ip} "
                        f"{command} {parameters[:40]} "
                        f"err: {repr(ee)} {str(ee)}")
            if not success and not cancelled and (cancel_event is None or not cancel_event.is_set()):
                _logger.debug(f"{ip}:{port} sleep for next try")
                await asyncio.sleep(0.1)
    response = None
    delta_total_time = uf.measurable_time() - total_start_time
    if success:
        response = buffer_list.rstrip(b'\x00')
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: success. "
            f"command {command} with parameter {parameters[:60]}."
            f" dt: {delta_total_time}")
    elif total_timeout_err:
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: total timeout. "
            f"command {command} with parameter {parameters[:60]}."
            f" dt: {delta_total_time}")
        err_msgs.append(f"Total timeout. limit {total_timeout}, real {delta_total_time}")
    else:
        _logger.info(
            f"[{api_request_id}] [ip {ip} port {port}] "
            f"[{try_times}/{retry}] "
            f"api finish: other error."
            f"command {command} with parameter {parameters[:60]}. "
            f" dt: {delta_total_time}"
            f"err: {err_msgs[-1][:100] if err_msgs else 'no err msg'}")
    if cancel_task is not None and not cancel_task.done():
        cancel_task.cancel()
        await cancel_task
    return CGMinerAPIResult(success, scantime, response, try_times, "\n".join(err_msgs))


async def wait_cancelable(coro_task, timeout, cancel_task):
    try:
        done_tasks, pending_tasks = await asyncio.wait(
            {coro_task, cancel_task} if cancel_task is not None else {coro_task},
            timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if cancel_task is not None and cancel_task in done_tasks:
            coro_task.cancel()
            await coro_task
            raise asyncio.CancelledError()
        elif coro_task in done_tasks:
            return coro_task.result()
        else:  # len(cancel_task) == 0
            coro_task.cancel()
            # await coro_task  # here we should NOT wait, because we should raise timeout, rather than cancelled
            raise asyncio.TimeoutError()
    except asyncio.CancelledError:
        coro_task.cancel()
        _logger.debug(f"wait_cancelable cancel exception {traceback.format_exc()}")
        raise


def canceled_result():
    return CGMinerAPIResult.error_result(time.time(), "has been canceled", code=CGMinerStatusCode.Cancelled)


class CGMinerAPI(object):
    default_first_timeout = 5

    @staticmethod
    def multiple_report_commands(
            ip, cmd_list,
            port=kDefaultPort,
            first_timeout=default_first_timeout,
            retry=0,
            total_timeout=30 * 60):
        """
        return dict. "result" bool, if result is False, 'raw' is original APIResult
        """
        mul_cmd_r = request_cgminer_api_by_sock(
            ip, "+".join(cmd_list), "",
            port, first_timeout, retry, total_timeout=total_timeout)
        return CGMinerAPI.split_multiple_report_api_result(cmd_list, mul_cmd_r)

    @staticmethod
    async def aio_multiple_report_commands(
            ip, cmd_list,
            port=kDefaultPort,
            first_timeout=default_first_timeout,
            retry=0,
            total_timeout=30 * 60):
        """
        return dict. "result" bool, if result is False, 'raw' is original APIResult
        """
        mul_cmd_r = await aio_request_cgminer_api_by_sock(
            ip, "+".join(cmd_list), "",
            port, first_timeout, retry, total_timeout=total_timeout)
        return CGMinerAPI.split_multiple_report_api_result(cmd_list, mul_cmd_r)

    @staticmethod
    def split_multiple_report_api_result(cmd_list, mul_cmd_r):
        is_success = mul_cmd_r.is_request_success()
        all_api_results = {"result": is_success}
        if is_success:
            for cmd in cmd_list:
                all_api_results[cmd] = CGMinerAPIResult(mul_cmd_r.result, mul_cmd_r.scan_timestamp,
                                                        mul_cmd_r.success_response_dict(cmd)[0],
                                                        mul_cmd_r.try_times, mul_cmd_r.msg)
        else:
            all_api_results['raw'] = mul_cmd_r
        return all_api_results

    @staticmethod
    def estats(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "estats", "", port, first_timeout, retry)

    @staticmethod
    def edevs(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "edevs", "", port, first_timeout, retry)

    @staticmethod
    def summary(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "summary", "", port, first_timeout, retry)

    @staticmethod
    def pools(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "pools", "", port, first_timeout, retry)

    @staticmethod
    def toggle_LED(ip, dev_id, mod_id, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "ascset", "%s,led,%s" % (dev_id, mod_id), port, first_timeout, retry)

    @staticmethod
    def turn_LED(ip, dev_id, mod_id, turn_on, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        # search 'strcasecmp(option, "led")' at cgminer driver
        return request_cgminer_api_by_sock(
            ip, "ascset", "%s,led,%s-%s" % (dev_id, mod_id, 1 if turn_on else 0),
            port, first_timeout, retry)

    @staticmethod
    def query_A10_LED(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        response = request_cgminer_api_by_sock(
            ip, "ascset", "0,led,0-255",
            port, first_timeout, retry, error_info=error_info)
        if response.result:
            msg = response.status_msg()
            return uf.parse_cgminer_bracket_format_str_into_json(msg).get('LED') == 1
        return None

    @staticmethod
    def toggle_debug(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        # ref cgminer api.c , search 'static void debugstate(' to go to debugstate function
        return request_cgminer_api_by_sock(ip, "debug", "d", port, first_timeout, retry)

    @staticmethod
    def get_debug_status(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "debug", "", port, first_timeout, retry)

    @staticmethod
    def turn_on_debug(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        debug_result = CGMinerAPI.get_debug_status(ip, port, first_timeout, retry)
        if debug_result.is_request_success():
            if not uf.str2bool(debug_result.debug()[0]['Debug']):
                CGMinerAPI.toggle_debug(ip, port, first_timeout, retry)
            return True
        else:
            return False

    @staticmethod
    def reboot(ip, dev_id, mod_id, port=kDefaultPort, first_timeout=default_first_timeout, retry=0):
        return request_cgminer_api_by_sock(ip, "ascset", "%s,reboot,%s" % (dev_id, mod_id), port, first_timeout, retry)

    @staticmethod
    def reboot_mm3(ip, last_when=0, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        return request_cgminer_api_by_sock(
            ip, "ascset", "0,reboot,%s" % last_when, port, first_timeout, retry, error_info=error_info)

    @staticmethod
    async def aio_reboot_mm3(
            ip, last_when=0, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        return await aio_request_cgminer_api_by_sock(
            ip, "ascset", "0,reboot,%s" % last_when, port, first_timeout, retry, error_info=error_info)

    @staticmethod
    def mm3_set_workmode(
            ip, workmode, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        return request_cgminer_api_by_sock(
            ip, "ascset", "0,workmode,%s" % workmode, port, first_timeout, retry, error_info=error_info)

    @staticmethod
    def version(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        return request_cgminer_api_by_sock(ip, "version", "", port, first_timeout, retry, error_info=error_info)

    @staticmethod
    async def aio_version(ip, port=kDefaultPort, first_timeout=default_first_timeout, retry=0, error_info=None):
        return await aio_request_cgminer_api_by_sock(
            ip, "version", "", port, first_timeout, retry, error_info=error_info)

    @staticmethod
    def mm3_upgrade(ip, uid, api_version, version, file_size, offset, payload_len, payload,
                    port=kDefaultPort,
                    first_timeout=default_first_timeout,
                    retry=0,
                    use_json_command=True):
        param_str = CGMinerAPI._prepare_upgrade_param(
            api_version, file_size, ip, offset, payload, payload_len, uid, version)
        return request_cgminer_api_by_sock(
            ip, "ascset", "0,upgrade," + param_str, port, first_timeout, retry)

    @staticmethod
    async def aio_mm3_upgrade(ip, uid, api_version, version, file_size, offset, payload_len, payload,
                              port=kDefaultPort,
                              first_timeout=default_first_timeout,
                              retry=0,
                              use_json_command=True):
        param_str = CGMinerAPI._prepare_upgrade_param(
            api_version, file_size, ip, offset, payload, payload_len, uid, version)
        return await aio_request_cgminer_api_by_sock(
            ip, "ascset", "0,upgrade," + param_str, port, first_timeout, retry)

    @staticmethod
    def _prepare_upgrade_param(api_version, file_size, ip, offset, payload, payload_len, uid, version):
        import random
        payload_dict = {}
        endianness = 'little'
        param = bytearray()
        endian_flag = 0b0  # 0 for little endian, 1 for big endian
        payload_dict['endian_flag'] = endian_flag
        api_ver = api_version
        payload_dict['api_ver'] = api_ver
        byte0 = (endian_flag << 7) | api_ver
        param.extend(uf.long_to_bytes(byte0, 1, endianness))
        header_len = 30  # header bytes count
        payload_dict['header_len'] = header_len
        param.extend(uf.long_to_bytes(header_len, 1, endianness))
        cmd_ID = random.randint(1, 65536 / 2)  # 2 bytes
        payload_dict['cmd_ID'] = cmd_ID
        param.extend(uf.long_to_bytes(cmd_ID, 2, endianness))
        sub_cmd = 0x0  # always 0
        payload_dict['sub_cmd'] = sub_cmd
        param.extend(uf.long_to_bytes(sub_cmd, 1, endianness))
        reserved1 = 0x0  # 3 bytes
        param.extend(uf.long_to_bytes(reserved1, 3, endianness))
        payload_dict['uid'] = uid
        param.extend(uf.long_to_bytes(uid, 4, endianness))
        version = version[:8]  # max allowed len is 8
        payload_dict['version'] = version
        param.extend(version.zfill(8).encode('latin1'))
        payload_dict['file_size'] = file_size
        param.extend(uf.long_to_bytes(file_size, 4, endianness))
        payload_dict['offset'] = offset
        param.extend(uf.long_to_bytes(offset, 4, endianness))
        payload_dict['payload_len'] = payload_len
        param.extend(uf.long_to_bytes(payload_len, 2, endianness))
        reserved2 = 0x0  # 2 bytes
        param.extend(uf.long_to_bytes(reserved2, 2, endianness))
        param.extend(payload)
        param_str = ''.join([hex(b)[2:].zfill(2) for b in param])
        _logger.debug(param_str[:100])
        _logger.debug("ip: %s pd: %s" % (ip, str(payload_dict)))
        return param_str
