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


from setuptools import setup
import pathlib

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()


setup(
    name='fms-core',
    version='0.0.2',
    packages=['fmsc'],
    url='https://github.com/Canaan-Creative/fms-core',
    license='Apache-2.0',
    author='Canaan',
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3 :: Only",
    ],
    author_email='',
    description='The core functions that Canaan FMS and other miner management systems '
                'needed to communicate with and control Avalon miners.',
    long_description=README,
    long_description_content_type="text/markdown",
    install_requires=['kaitaistruct'],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "fmsc=fmsc.__main__:main",
        ]
    },
)
