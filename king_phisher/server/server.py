#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/server/server.py
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

import json
import logging
import os
import random
import shutil
import sqlite3
import string
import threading

from AdvancedHTTPServer import *
from AdvancedHTTPServer import build_server_from_config
from AdvancedHTTPServer import SectionConfigParser

from king_phisher import xor
from king_phisher.server import authenticator
from king_phisher.server import rpcmixin

__version__ = '0.0.1'

make_uid = lambda: ''.join(random.choice(string.ascii_letters + string.digits) for x in range(24))

def build_king_phisher_server(config, section_name):
	forked_authenticator = authenticator.ForkedAuthenticator()
	king_phisher_server = build_server_from_config(config, 'server', ServerClass = KingPhisherServer, HandlerClass = KingPhisherRequestHandler)
	king_phisher_server.serve_files = True
	king_phisher_server.serve_files_list_directories = False
	king_phisher_server.serve_robots_txt = True
	king_phisher_server.http_server.authenticator = forked_authenticator
	king_phisher_server.http_server.config = SectionConfigParser('server', config)
	king_phisher_server.http_server.throttle_semaphore = threading.Semaphore(2)
	return king_phisher_server

class KingPhisherRequestHandler(rpcmixin.KingPhisherRequestHandlerRPCMixin, AdvancedHTTPServerRequestHandler):
	def install_handlers(self):
		super(KingPhisherRequestHandler, self).install_handlers()
		self.database = self.server.database
		self.database_lock = threading.RLock()
		self.config = self.server.config
		self.handler_map['^kpdd$'] = self.handle_deaddrop_visit

	def do_GET(self, *args, **kwargs):
		self.server.throttle_semaphore.acquire()
		try:
			super(KingPhisherRequestHandler, self).do_GET(*args, **kwargs)
		except:
			raise
		finally:
			self.server.throttle_semaphore.release()

	def do_POST(self, *args, **kwargs):
		self.server.throttle_semaphore.acquire()
		try:
			super(KingPhisherRequestHandler, self).do_POST(*args, **kwargs)
		except:
			raise
		finally:
			self.server.throttle_semaphore.release()

	def do_RPC(self, *args, **kwargs):
		self.server.throttle_semaphore.acquire()
		try:
			super(KingPhisherRequestHandler, self).do_RPC(*args, **kwargs)
		except:
			raise
		finally:
			self.server.throttle_semaphore.release()

	def custom_authentication(self, username, password):
		return self.server.authenticator.authenticate(username, password)

	def check_authorization(self):
		if self.command in ['GET', 'POST']:
			return True
		if self.client_address[0] != '127.0.0.1':
			return False
		return super(KingPhisherRequestHandler, self).check_authorization()

	def respond_file(self, file_path, attachment = False, query = {}):
		file_path = os.path.abspath(file_path)
		try:
			file_obj = open(file_path, 'rb')
		except IOError:
			self.respond_not_found()
			return None
		self.send_response(200)
		self.send_header('Content-Type', self.guess_mime_type(file_path))
		fs = os.fstat(file_obj.fileno())
		self.send_header('Content-Length', str(fs[6]))
		if attachment:
			file_name = os.path.basename(file_path)
			self.send_header('Content-Disposition', 'attachment; filename=' + file_name)
		self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))

		get_query_parameter = lambda p: query.get(p, [None])[0]
		msg_id = get_query_parameter('id')
		if not msg_id:
			kp_cookie_name = self.config.get('cookie_name', 'KPID')
			if kp_cookie_name in self.cookies:
				with self.get_cursor() as cursor:
					visit_id = self.cookies[kp_cookie_name].value
					cursor.execute('SELECT message_id FROM visits WHERE id = ?', (visit_id,))
					msg_id = cursor.fetchone()[0]
		if msg_id:
			try:
				self.handle_visit(query, msg_id)
			except Exception as err:
				# TODO: log execeptions here
				pass

		self.end_headers()
		shutil.copyfileobj(file_obj, self.wfile)
		file_obj.close()
		return

	def handle_deaddrop_visit(self, query):
		data = query['token'][0]
		data = data.decode('base64')
		data = xor.xor_decode(data)
		data = json.loads(data)

		deployment_id = data.get('deaddrop_id')
		with self.get_cursor() as cursor:
			cursor.execute('SELECT campaign_id FROM deaddrop_deployments WHERE id = ?', (deployment_id,))
			campaign_id = cursor.fetchone()
			if not campaign_id:
				self.send_response(200)
				self.end_headers()
				return
			campaign_id = campaign_id[0]

		local_username = data.get('local_username')
		local_hostname = data.get('local_hostname')
		if campaign_id == None or local_username == None or local_hostname == None:
			return
		local_ip_addresses = data.get('local_ip_addresses')
		if isinstance(local_ip_addresses, (list, tuple)):
			local_ip_addresses = ' '.join(local_ip_addresses)

		with self.get_cursor() as cursor:
			cursor.execute('SELECT id FROM deaddrop_connections WHERE deployment_id = ? AND local_username = ? AND local_hostname = ?', (deployment_id, local_username, local_hostname))
			drop_id = cursor.fetchone()
			if drop_id:
				drop_id = drop_id[0]
				cursor.execute('UPDATE deaddrop_connections SET visit_count = visit_count + 1, last_visit = CURRENT_TIMESTAMP WHERE id = ?', (drop_id,))
				self.send_response(200)
				self.end_headers()
				return
			values = (deployment_id, campaign_id, self.client_address[0], local_username, local_hostname, local_ip_addresses)
			cursor.execute('INSERT INTO deaddrop_connections (deployment_id, campaign_id, visitor_ip, local_username, local_hostname, local_ip_addresses) VALUES (?, ?, ?, ?, ?, ?)', values)
		self.send_response(200)
		self.end_headers()
		return

	def handle_visit(self, query, msg_id):
		with self.get_cursor() as cursor:
			cursor.execute('SELECT campaign_id FROM messages WHERE id = ?', (msg_id,))
			campaign_id = cursor.fetchone()
			if not campaign_id:
				return
			campaign_id = campaign_id[0]

		get_query_parameter = lambda p: query.get(p, [None])[0]
		kp_cookie_name = self.config.get('cookie_name', 'KPID')
		if not kp_cookie_name in self.cookies:
			visit_id = make_uid()
			cookie = "{0}={1}; Path=/; HttpOnly".format(kp_cookie_name, visit_id)
			self.send_header('Set-Cookie', cookie)
			with self.get_cursor() as cursor:
				client_ip = self.client_address[0]
				user_agent = (self.headers.getheader('user-agent') or '')
				cursor.execute('INSERT INTO visits (id, message_id, campaign_id, visitor_ip, visitor_details) VALUES (?, ?, ?, ?, ?)', (visit_id, msg_id, campaign_id, client_ip, user_agent))
		else:
			visit_id = self.cookies[kp_cookie_name].value
			with self.get_cursor() as cursor:
				cursor.execute('UPDATE visits SET visit_count = visit_count + 1, last_visit = CURRENT_TIMESTAMP WHERE id = ?', (visit_id,))

		username = (get_query_parameter('username') or get_query_parameter('user') or get_query_parameter('u'))
		if not username:
			return
		password = (get_query_parameter('password') or get_query_parameter('pass') or get_query_parameter('p'))
		password = (password or '')
		with self.get_cursor() as cursor:
			cursor.execute('INSERT INTO credentials (visit_id, message_id, campaign_id, username, password) VALUES (?, ?, ?, ?, ?)', (visit_id, msg_id, campaign_id, username, password))

class KingPhisherServer(AdvancedHTTPServer):
	def __init__(self, *args, **kwargs):
		super(KingPhisherServer, self).__init__(*args, **kwargs)
		self.database = None
		self.logger = logging.getLogger('KingPhisher.Server')

	def load_database(self, database_file):
		if database_file == ':memory:':
			db = database.create_database(database_file)
		else:
			db = sqlite3.connect(database_file, check_same_thread = False)
		self.database = db
		self.http_server.database = db
