#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/utilities.py
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
#  * Neither the name of the project nor the names of its
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

import collections
import functools
import os
import subprocess
import sys
import time

def timedef_to_seconds(timedef):
	converter_order = ['w', 'd', 'h', 'm', 's']
	converters = {
		'w': 604800,
		'd': 86400,
		'h': 3600,
		'm': 60,
		's': 1
	}
	timedef = timedef.lower()
	if timedef.isdigit():
		return int(timedef)
	elif len(timedef) == 0:
		return 0
	seconds = -1
	for spec in converter_order:
		timedef = timedef.split(spec)
		if len(timedef) == 1:
			timedef = timedef[0]
			continue
		elif len(timedef) > 2 or not timedef[0].isdigit():
			seconds = -1
			break
		adjustment = converters[spec]
		seconds = max(seconds, 0)
		seconds += (int(timedef[0]) * adjustment)
		timedef = timedef[1]
		if not len(timedef):
			break
	if seconds < 0:
		raise ValueError('invalid time format')
	return seconds

class cache(object):
	def __init__(self, timeout):
		if isinstance(timeout, (str, unicode)):
			timeout = timedef_to_seconds(timeout)
		self.cache_timeout = timeout
		self.__cache = {}

	def __call__(self, *args):
		if not hasattr(self, '_target_function'):
			self._target_function = args[0]
			return self
		self.cache_clean()
		if not isinstance(args, collections.Hashable):
			return self._target_function(*args)
		result, expiration = self.__cache.get(args, (None, 0))
		if expiration > time.time():
			return result
		result = self._target_function(*args)
		self.__cache[args] = (result, time.time() + self.cache_timeout)
		return result

	def __repr__(self):
		return "<cached function {0}>".format(self._target_function.__name__)

	def cache_clean(self):
		now = time.time()
		keys_for_removal = []
		for key, (value, expiration) in self.__cache.items():
			if expiration < now:
				keys_for_removal.append(key)
		for key in keys_for_removal:
			del self.__cache[key]

	def cache_clear(self):
		self.__cache = {}

def open_uri(uri):
	proc_args = []
	startupinfo = None
	if sys.platform.startswith('win'):
		proc_args.append(which('cmd.exe'))
		proc_args.append('/c')
		proc_args.append('start')
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		startupinfo.wShowWindow = subprocess.SW_HIDE
	elif which('gvfs-open'):
		proc_args.append(which('gvfs-open'))
	elif which('xdg-open'):
		proc_args.append(which('xdg-open'))
	else:
		raise RuntimeError('could not find suitable application to open uri')
	proc_args.append(uri)
	proc_h = subprocess.Popen(proc_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
	return proc_h.wait() == 0

def server_parse(server, default_port):
	server = server.split(':')
	host = server[0]
	if len(server) == 1:
		return (host, default_port)
	else:
		port = server[1]
		if not port:
			port = default_port
		else:
			port = int(port)
		return (host, port)

def unique(seq, key=None):
	if key is None:
		key = lambda x: x
	preserved_type = type(seq)
	seen = {}
	result = []
	for item in seq:
		marker = key(item)
		if marker in seen:
			continue
		seen[marker] = 1
		result.append(item)
	return preserved_type(result)

def which(program):
	is_exe = lambda fpath: (os.path.isfile(fpath) and os.access(fpath, os.X_OK))
	if is_exe(program):
		return program
	for path in os.environ["PATH"].split(os.pathsep):
		path = path.strip('"')
		exe_file = os.path.join(path, program)
		if is_exe(exe_file):
			return exe_file
	return None
