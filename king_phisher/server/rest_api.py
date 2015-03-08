#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/server/rest_api.py
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

import json

from king_phisher import geoip
from king_phisher import sms
from king_phisher import utilities
from king_phisher.third_party.AdvancedHTTPServer import AdvancedHTTPServerRegisterPath

__all__ = ['generate_token']

REST_API_BASE = '_/api/'
"""The base URI path for REST API requests."""
REST_HANDLER = 'KingPhisherRequestHandler'
"""The :py:class:`~king_phisher.third_party.AdvancedHTTPServer.AdvancedHTTPServerRequestHandler` class to register REST API handlers to."""

def generate_token():
	"""
	Generate the token to be checked when REST API requests are made.

	:return: The API token
	:rtype: str
	"""
	return utilities.random_string(24)

def rest_handler(handle_function):
	"""
	A function for decorating REST API handlers. The function checks the API
	token in the request and encodes the handler response in JSON to be sent to
	the client.

	:param handle_function: The REST API handler.
	"""
	def wrapped(handler, params):
		if not handler.config.get('server.rest_api.enabled'):
			handler.respond_unauthorized()
			return
		if handler.config.get('server.rest_api.token') == None or handler.config.get('server.rest_api.token') != handler.get_query('token'):
			handler.respond_unauthorized()
			return
		response = dict(result=handle_function(handler, params))
		response = json.dumps(response, sort_keys=True, indent=2, separators=(',', ': '))
		handler.send_response(200)
		handler.send_header('Content-Type', 'application/json')
		handler.send_header('Content-Length', str(len(response)))
		handler.end_headers()
		handler.wfile.write(response)
		return
	return wrapped

@AdvancedHTTPServerRegisterPath(REST_API_BASE + 'geoip/lookup', REST_HANDLER)
@rest_handler
def rest_api_geoip_lookup(handler, params):
	ip = handler.get_query('ip')
	assert ip
	return geoip.lookup(ip)

@AdvancedHTTPServerRegisterPath(REST_API_BASE + 'sms/send', REST_HANDLER)
@rest_handler
def rest_api_sms_send(handler, params):
	sms.send_sms(
		handler.get_query('message'),
		handler.get_query('phone_number'),
		handler.get_query('carrier'),
		handler.get_query('from_address')
	)
	return 'sent'
