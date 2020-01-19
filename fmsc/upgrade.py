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

import typing

from .aioupgrade import UpgradeStatus, aio_mm3_upgrade, UpgradeResults
from .aupfile import AUPFile


def upgrade_firmware(ip: str, port: int, firmware_file_path: str, timeout: int = 12*60):
    from fmsc.cliprogressbar import printProgressBar

    def _on_progress(ratio: typing.Union[float, UpgradeResults], status: UpgradeStatus):
        printProgressBar(ratio if isinstance(ratio, float) else 1.0, 1.0, suffix=f"{status}")

    aup_file = AUPFile(firmware_file_path)
    aup_file_payload = aup_file.file_content_binary()
    version = aup_file.header().firmware_ver()

    return asyncio.run(aio_mm3_upgrade(
        ip,
        port=port,
        api_version=0,
        version=version,
        payload=aup_file_payload,
        timeout=timeout,
        enable_pre_ver_check=True,
        progress_report_fxn=_on_progress,
        supported_hwtype_list=aup_file.header().all_supported_hwtype_list(),
        supported_swtype_list=aup_file.header().all_supported_swtype_list(),
        aup_file=aup_file))
