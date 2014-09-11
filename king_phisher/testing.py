#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/testing.py
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

import httplib
import os
import random
import string
import threading
import unittest

from king_phisher import configuration
from king_phisher import find
from king_phisher.server.server import *

__all__ = [
	'TEST_MESSAGE_TEMPLATE',
	'TEST_MESSAGE_TEMPLATE_INLINE_IMAGE',
	'KingPhisherServerTestCase'
]

TEST_MESSAGE_TEMPLATE_INLINE_IMAGE = '/path/to/fake/image.png'
"""A string with the path to a file used as an inline image in the :py:data:`.TEST_MESSAGE_TEMPLATE`."""

TEST_MESSAGE_TEMPLATE = """
<html>
<body>
	Hello {{ client.first_name }} {{ client.last_name }},<br />
	<br />
	Lorem ipsum dolor sit amet, inani assueverit duo ei. Exerci eruditi nominavi
	ei eum, vim erant recusabo ex, nostro vocibus minimum no his. Omnesque
	officiis his eu, sensibus consequat per cu. Id modo vidit quo, an has
	detracto intellegat deseruisse. Vis ut novum solet complectitur, ei mucius
	tacimates sit.
	<br />
	Duo veniam epicuri cotidieque an, usu vivendum adolescens ei, eu ius soluta
	minimum voluptua. Eu duo numquam nominavi deterruisset. No pro dico nibh
	luptatum. Ex eos iriure invenire disputando, sint mutat delenit mei ex.
	Mundi similique persequeris vim no, usu at natum philosophia.
	<a href="{{ url.webserver }}">{{ client.company_name }} HR Enroll</a><br />
	<br />
	{{ inline_image('""" + TEST_MESSAGE_TEMPLATE_INLINE_IMAGE + """') }}
	{{ tracking_dot_image_tag }}
</body>
</html>
"""
"""A string representing a message template that can be used for testing."""

class KingPhisherRequestHandlerTest(KingPhisherRequestHandler):
	def custom_authentication(self, *args, **kwargs):
		return True

class KingPhisherServerTestCase(unittest.TestCase):
	"""
	This class can be inherited to automatically set up a King Phisher server
	instance configured in a way to be suitable for testing purposes.
	"""
	def setUp(self):
		find.data_path_append('data/server')
		web_root = os.path.join(os.getcwd(), 'data', 'server', 'king_phisher')
		config = configuration.Configuration(find.find_data_file('server_config.yml'))
		config.set('server.address.port', random.randint(2000, 10000))
		config.set('server.database', ':memory:')
		config.set('server.web_root', web_root)
		self.config = config
		self.server = build_king_phisher_server(config, HandlerClass=KingPhisherRequestHandlerTest)
		self.assertIsInstance(self.server, KingPhisherServer)
		self.server.init_database(config.get('server.database'))
		self.server_thread = threading.Thread(target=self.server.serve_forever)
		self.server_thread.daemon = True
		self.server_thread.start()
		self.assertTrue(self.server_thread.is_alive())
		self.shutdown_requested = False

	def assertHTTPStatus(self, http_response, status):
		"""
		Check an HTTP response to ensure that the correct HTTP status code is
		specified.

		:param http_response: The response object to check.
		:type http_response: :py:class:`httplib.HTTPResponse`
		:param int status: The status to check for.
		"""
		self.assertIsInstance(http_response, httplib.HTTPResponse)
		error_message = "HTTP Response received status {0} when {1} was expected".format(http_response.status, status)
		self.assertEqual(http_response.status, status, msg=error_message)

	def http_request(self, resource, method='GET', include_id=True):
		"""
		Make an HTTP request to the specified resource on the test server.

		:param str resource: The resource to send the request to.
		:param str method: The HTTP method to use for the request.
		:param bool include_id: Whether to include the the id parameter.
		:return: The servers HTTP response.
		:rtype: :py:class:`httplib.HTTPResponse`
		"""
		if include_id:
			resource += "{0}id={1}".format('&' if '?' in resource else '?', self.config.get('server.secret_id'))
		conn = httplib.HTTPConnection('localhost', self.config.get('server.address.port'))
		conn.request(method, resource)
		response = conn.getresponse()
		conn.close()
		return response

	def web_root_files(self, limit=None):
		"""
		A generator object that yeilds valid files which are contained in the
		web root of the test server instance. This can be used to find resources
		which the server should process as files. The function will fail if
		no files can be found in the web root.

		:param int limit: A limit to the number of files to return.
		"""
		limit = (limit or float('inf'))
		philes_yielded = 0
		web_root = self.config.get('server.web_root')
		self.assertTrue(os.path.isdir(web_root), msg='The test web root does not exist')
		directories = filter(lambda p: os.path.isdir(os.path.join(web_root, p)), os.listdir(web_root))
		for directory in directories:
			full_directory = os.path.join(web_root, directory)
			for phile in filter(lambda p: os.path.isfile(os.path.join(full_directory, p)), os.listdir(full_directory)):
				phile = os.path.join(directory, phile)
				if philes_yielded < limit:
					yield phile
				philes_yielded += 1
		self.assertGreater(philes_yielded, 0, msg='No files were found in the web root')

	def tearDown(self):
		if not self.shutdown_requested:
			self.assertTrue(self.server_thread.is_alive())
		self.server.shutdown()
		self.server_thread.join(5.0)
		self.assertFalse(self.server_thread.is_alive())
		del self.server
