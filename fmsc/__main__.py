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

"""Query or control Avalon miners
Usage:
------
    $ fmsc -h
More information is available at:
- https://github.com/Canaan-Creative/fms-core
Version:
--------
- fmsc v0.0.1
"""
import argparse
import logging
# Standard library imports
import sys

# fmsc imports
import fmsc
from fmsc import upgrade

_logger = logging.getLogger(__file__)


def upgrade_miner(args):
    from fmsc.aioupgrade import UpgradeResults
    success: bool = False
    upgrade_result: UpgradeResults = UpgradeResults.unexpected_error
    try:
        success, upgrade_result = upgrade.upgrade_firmware(args.ip, args.port, args.file, timeout=args.timeout)
    finally:
        print(f"upgrade {args.ip}:{args.port} firmware to {args.file} finish: "
              f"{'success' if success else 'failed'} with {upgrade_result}")


def main():  # type: () -> None
    """Query or control Avalon miners"""
    parser = argparse.ArgumentParser(prog=fmsc.__name__, description='Query or control Avalon miners.')
    parser.add_argument('--log', type=str, choices=['debug', 'info', 'error'], default='info',
                        help='logging level, default is %(default)s')
    subparsers = parser.add_subparsers(
        title='subcommands',
        description='valid subcommands',
        help='sub commands list')
    upgrade_parser = subparsers.add_parser('upgrade',
                                           help='upgrade firmware for one Avalon miner')
    upgrade_parser.add_argument('--ip', '-I', type=str,
                                help='Avalon miner IP address, such as 192.168.1.123')
    upgrade_parser.add_argument('--port', '-P', type=int, default=4028,
                                help='Avalon miner API port, default is %(default)s')
    upgrade_parser.add_argument('--file', '-F', type=str,
                                help='Avalon miner firmware file path')
    upgrade_parser.add_argument('--timeout', '-T', type=int, default=12 * 60,
                                help="Upgrade timeout. It's unit is seconds. default is %(default)s")
    upgrade_parser.set_defaults(func=upgrade_miner)

    args = parser.parse_args() if len(sys.argv) > 1 else parser.parse_args(['-h'])

    logging_level = logging.DEBUG if args.log == 'debug' else (logging.ERROR if args.log == 'error' else logging.INFO)
    logging.basicConfig(level=logging_level)

    if hasattr(args, 'func'):
        args.func(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _logger.exception(f"{fmsc.__name__} main uncaught exception")
