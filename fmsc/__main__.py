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
    $ fmsc [sub command] [options] [parameters ...]
Upgrade firmware:
    $ fmsc upgrade <ip> [port: default 4028]
Available options are:
    -h, --help         Show this help
More information is available at:
- https://github.com/Canaan-Creative/fms-core
Version:
--------
- fmsc v0.0.1
"""
# Standard library imports
import sys
import argparse

# fmsc imports
import fmsc
from fmsc import upgrade


def upgrade_miner(args):
    print(f"args.ip {args.ip}, args.port {args.port}, args.file {args.file}")


def main():  # type: () -> None
    """Query or control Avalon miners"""
    parser = argparse.ArgumentParser(prog=fmsc.__name__, description='Query or control Avalon miners.')
    subparsers = parser.add_subparsers(
        title='subcommands',
        description='valid subcommands',
        help='sub commands list')
    upgrade_parser = subparsers.add_parser('upgrade', help='upgrade firmware for one Avalon miner')
    upgrade_parser.add_argument('--ip', '-I', type=str, help='Avalon miner IP address, such as 192.168.1.123')
    upgrade_parser.add_argument('--port', '-P', type=int, default=4028, help='Avalon miner API port, default is %(default)s')
    upgrade_parser.add_argument('--file', '-F', type=str, help='Avalon miner firmware file path')
    upgrade_parser.set_defaults(func=upgrade_miner)

    args = parser.parse_args() if len(sys.argv) > 1 else parser.parse_args(['-h'])
    if hasattr(args, 'func'):
        args.func(args)


if __name__ == "__main__":
    main()
