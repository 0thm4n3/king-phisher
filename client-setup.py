#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  client-setup.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the  nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

from distutils.core import setup
import os

from king_phisher.client import client

data_files_src_prefix = os.path.join('data', 'client', 'king_phisher')
if os.path.isdir(data_files_src_prefix):
	data_files = os.listdir(data_files_src_prefix)
	data_files = map(lambda x: os.path.join(data_files_src_prefix, x), data_files)
else:
	data_files = []

setup(
	name = 'King Phisher Client',
	version = str(client.__version__),
	description = 'King Phisher Client GUI Frontened',
	author = 'Spencer McIntyre',
	maintainer = 'Spencer McIntyre',
	packages = [
		'king_phisher',
		'king_phisher.client',
		'king_phisher.client.tabs',
	],
	scripts = ['KingPhisher'],
	data_files = [(os.path.join('share', 'king_phisher'), data_files)],
)
