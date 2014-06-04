#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/templates.py
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

import datetime
import logging
import os

from king_phisher import version

import jinja2

__all__ = ['KingPhisherTemplateEnvironment']

class KingPhisherTemplateEnvironment(jinja2.Environment):
	def __init__(self, loader=None, global_vars=None):
		self.logger = logging.getLogger('KingPhisher.TemplateEnvironment')
		autoescape = lambda name: isinstance(name, (str, unicode)) and os.path.splitext(name)[1][1:] in ('htm', 'html', 'xml')
		extensions = ['jinja2.ext.autoescape']
		super(KingPhisherTemplateEnvironment, self).__init__(autoescape=autoescape, extensions=extensions, loader=loader, trim_blocks=True)

		self.filters['strftime'] = self._filter_strftime
		self.filters['tomorrow'] = lambda dt: dt + datetime.timedelta(days=1)
		self.filters['next_week'] = lambda dt: dt + datetime.timedelta(weeks=1)
		self.filters['yesterday'] = lambda dt: dt + datetime.timedelta(days=-1)
		self.filters['last_week'] = lambda dt: dt + datetime.timedelta(weeks=-1)
		self.globals['version'] = version.version
		if global_vars:
			for key, value in global_vars.items():
				self.globals[key] = value

	@property
	def standard_variables(self):
		std_vars = {
			'time': {
				'local': datetime.datetime.now(),
				'utc': datetime.datetime.utcnow()
			}
		}
		return std_vars

	def _filter_strftime(self, dt, fmt):
		try:
			result = dt.strftime(fmt)
		except ValueError:
			self.logger.error("invalid time format '{0}'".format(fmt))
			result = ''
		return result
