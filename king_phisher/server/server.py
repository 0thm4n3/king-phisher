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

import binascii
import json
import logging
import os
import random
import shutil
import string
import threading

from king_phisher import find
from king_phisher import job
from king_phisher import sms
from king_phisher import templates
from king_phisher import xor
from king_phisher.server import authenticator
from king_phisher.server import database
from king_phisher.server import server_rpc
from king_phisher.third_party.AdvancedHTTPServer import *
from king_phisher.third_party.AdvancedHTTPServer import build_server_from_config

import jinja2

make_uid = lambda: ''.join(random.choice(string.ascii_letters + string.digits) for x in range(24))
"""Create a unique identifier string."""

def build_king_phisher_server(config, ServerClass=None, HandlerClass=None):
	"""
	Build a server from a provided :py:class:`.Configuration`
	instance. If a ServerClass or HandlerClass is specified, then the
	object must inherit from the corresponding KingPhisherServer base
	class.

	:param config: Configuration to retrieve settings from.
	:type config: :py:class:`.Configuration`
	:param ServerClass: Alternative server class to use.
	:type ServerClass: :py:class:`.KingPhisherServer`
	:param HandlerClass: Alternative handler class to use.
	:type HandlerClass: :py:class:`.KingPhisherRequestHandler`
	:return: A configured server instance.
	:rtype: :py:class:`.KingPhisherServer`
	"""
	ServerClass = (ServerClass or KingPhisherServer)
	HandlerClass = (HandlerClass or KingPhisherRequestHandler)
	# Set config defaults
	if not config.has_option('server.secret_id'):
		config.set('server.secret_id', make_uid())
	address = (config.get('server.address.host'), config.get('server.address.port'))
	server = ServerClass(config, HandlerClass, address=address)
	if config.has_option('server.server_header'):
		server.server_version = config.get('server.server_header')
	return server

class KingPhisherErrorAbortRequest(Exception):
	"""
	An exception that can be raised which when caught will cause the handler to
	immediately stop processing the current request.
	"""
	pass

class KingPhisherRequestHandler(server_rpc.KingPhisherRequestHandlerRPC, AdvancedHTTPServerRequestHandler):
	def __init__(self, *args, **kwargs):
		# this is for attribute documentation
		self.config = None
		"""The main King Phisher server :py:class:`.Configuration` instance."""
		self.database = None
		"""The :py:class:`.KingPhisherDatabase` instance."""
		self.path = None
		"""The resource path of the current HTTP request."""
		super(KingPhisherRequestHandler, self).__init__(*args, **kwargs)

	def install_handlers(self):
		self.logger = logging.getLogger('KingPhisher.Server.RequestHandler')
		super(KingPhisherRequestHandler, self).install_handlers()
		self.database = self.server.database
		self.config = self.server.config
		regex_prefix = '^'
		if self.config.get('server.vhost_directories'):
			regex_prefix += '[\w\.\-]+\/'
		self.handler_map[regex_prefix + 'kpdd$'] = self.handle_deaddrop_visit
		self.handler_map[regex_prefix + 'kp\\.js$'] = self.handle_javascript_hook

		tracking_image = self.config.get('server.tracking_image')
		tracking_image = tracking_image.replace('.', '\\.')
		self.handler_map[regex_prefix + tracking_image + '$'] = self.handle_email_opened

	def issue_alert(self, alert_text, campaign_id=None):
		"""
		Send an SMS alert. If no *campaign_id* is specified all users
		with registered SMS information will receive the alert otherwise
		only users subscribed to the campaign specified.

		:param str alert_text: The message to send to subscribers.
		:param int campaign_id: The campaign subscribers to send the alert to.
		"""
		campaign_name = None
		with self.get_cursor() as cursor:
			if campaign_id:
				cursor.execute('SELECT name FROM campaigns WHERE id = ?', (campaign_id,))
				campaign_name = cursor.fetchone()[0]
				cursor.execute('SELECT user_id FROM alert_subscriptions WHERE campaign_id = ?', (campaign_id,))
			else:
				cursor.execute('SELECT id FROM users WHERE phone_number IS NOT NULL AND phone_carrier IS NOT NULL')
			user_ids = map(lambda user_id: user_id[0], cursor.fetchall())
		if campaign_name != None and '{campaign_name}' in alert_text:
			alert_text = alert_text.format(campaign_name=campaign_name)
		for user_id in user_ids:
			with self.get_cursor() as cursor:
				cursor.execute('SELECT phone_number, phone_carrier FROM users WHERE id = ?', (user_id,))
				number, carrier = cursor.fetchone()
			self.server.logger.debug("sending alert SMS message to {0} ({1})".format(number, carrier))
			sms.send_sms(alert_text, number, carrier, 'donotreply@kingphisher.local')

	def adjust_path(self):
		"""Adjust the :py:attr:`~.KingPhisherRequestHandler.path` attribute based on multiple factors."""
		if not self.config.get('server.vhost_directories'):
			return
		if not self.vhost:
			raise KingPhisherErrorAbortRequest()
		if self.vhost in ['localhost', '127.0.0.1'] and self.client_address[0] != '127.0.0.1':
			raise KingPhisherErrorAbortRequest()
		self.path = '/' + self.vhost + self.path

	def _do_http_method(self, *args, **kwargs):
		self.server.throttle_semaphore.acquire()
		try:
			if self.command != 'RPC':
				self.adjust_path()
			if self.command == 'HEAD':
				http_method_handler = getattr(super(KingPhisherRequestHandler, self), 'do_GET')
			else:
				http_method_handler = getattr(super(KingPhisherRequestHandler, self), 'do_' + self.command)
			http_method_handler(*args, **kwargs)
		except KingPhisherErrorAbortRequest:
			self.respond_not_found()
		except:
			raise
		finally:
			self.server.throttle_semaphore.release()
	do_GET = _do_http_method
	do_HEAD = _do_http_method
	do_POST = _do_http_method
	do_RPC = _do_http_method

	def get_query_parameter(self, parameter):
		"""
		Get a parameter from the current request's query information.

		:param str parameter: The parameter to retrieve the value for.
		:return: The value of it exists.
		:rtype: str
		"""
		return self.query_data.get(parameter, [None])[0]

	def get_template_vars_client(self):
		"""
		Build a dictionary of variables for a client with an associated
		campaign.

		:return: The client specific template variables.
		:rtype: dict
		"""
		if not self.message_id:
			return None
		with self.get_cursor() as cursor:
			cursor.execute('SELECT target_email, company_name, first_name, last_name, trained FROM messages WHERE id = ?', (self.message_id,))
			result = cursor.fetchone()
		if not result:
			return None
		client_vars = {}
		client_vars['email'] = result[0]
		client_vars['company_name'] = result[1]
		client_vars['first_name'] = result[2]
		client_vars['last_name'] = result[3]
		client_vars['is_trained'] = bool(result[4])
		client_vars['message_id'] = self.message_id
		client_vars['visit_count'] = self.query_count('SELECT COUNT(id) FROM visits WHERE message_id = ?', (self.message_id,))
		if self.visit_id:
			client_vars['visit_id'] = self.visit_id
		else:
			# If the visit_id is not set then this is a new visit so increment the count preemptively
			client_vars['visit_count'] += 1
		return client_vars

	def custom_authentication(self, username, password):
		return self.server.forked_authenticator.authenticate(username, password)

	def check_authorization(self):
		# don't require authentication for non-RPC requests
		if self.command != 'RPC':
			return True
		# deny anything not GET or POST if it's not from 127.0.0.1
		if self.client_address[0] != '127.0.0.1':
			return False
		return super(KingPhisherRequestHandler, self).check_authorization()

	@property
	def campaign_id(self):
		"""
		The campaign id that is associated with the current request's
		visitor. This is retrieved by looking up the
		:py:attr:`~.KingPhisherRequestHandler.message_id` value in the
		database. If no campaign is associated, this value is None.
		"""
		if hasattr(self, '_campaign_id'):
			return self._campaign_id
		self._campaign_id = None
		if self.message_id:
			with self.get_cursor() as cursor:
				cursor.execute('SELECT campaign_id FROM messages WHERE id = ?', (self.message_id,))
				result = cursor.fetchone()
			if result:
				self._campaign_id = result[0]
		return self._campaign_id

	@property
	def message_id(self):
		"""
		The message id that is associated with the current request's
		visitor. This is retrieved by looking at an 'id' parameter in the
		query and then by checking the
		:py:attr:`~.KingPhisherRequestHandler.visit_id` value in the
		database. If no message id is associated, this value is None.
		"""
		if hasattr(self, '_message_id'):
			return self._message_id
		msg_id = self.get_query_parameter('id')
		if not msg_id and self.visit_id:
			with self.get_cursor() as cursor:
				cursor.execute('SELECT message_id FROM visits WHERE id = ?', (self.visit_id,))
				result = cursor.fetchone()
			if result:
				msg_id = result[0]
		self._message_id = msg_id
		return self._message_id

	@property
	def visit_id(self):
		"""
		The visit id that is associated with the current request's
		visitor. This is retrieved by looking for the King Phisher cookie.
		If no cookie is set, this value is None.
		"""
		if hasattr(self, '_visit_id'):
			return self._visit_id
		self._visit_id = None
		kp_cookie_name = self.config.get('server.cookie_name')
		if kp_cookie_name in self.cookies:
			self._visit_id = self.cookies[kp_cookie_name].value
		return self._visit_id

	@property
	def vhost(self):
		"""The value of the Host HTTP header."""
		return self.headers.get('Host')

	def respond_file(self, file_path, attachment=False, query={}):
		self._respond_file_check_id()
		file_path = os.path.abspath(file_path)
		file_ext = os.path.splitext(file_path)[1][1:]
		if attachment or not file_ext in ['hta', 'htm', 'html', 'txt']:
			self._respond_file_raw(file_path, attachment)
			return
		try:
			template = self.server.template_env.get_template(os.path.relpath(file_path, self.server.serve_files_root))
		except jinja2.exceptions.TemplateError, IOError:
			raise KingPhisherErrorAbortRequest()

		template_vars = {
			'client': {
				'address': self.client_address[0]
			},
			'server': {
				'hostname': self.vhost,
				'address': self.connection.getsockname()[0]
			}
		}
		template_vars.update(self.server.template_env.standard_variables)
		template_vars['client'].update(self.get_template_vars_client() or {})
		try:
			template_data = template.render(template_vars)
		except jinja2.TemplateError as error:
			self.server.logger.error("jinja2 template '{0}' render failed: {1} {2}".format(template.name, error.__class__.__name__, error.message))
			raise KingPhisherErrorAbortRequest()

		fs = os.stat(template.filename)
		mime_type = self.guess_mime_type(file_path)
		if mime_type.startswith('text'):
			mime_type = mime_type + '; charset=utf-8'
		self.send_response(200)
		self.send_header('Content-Type', mime_type)
		self.send_header('Content-Length', str(len(template_data)))
		self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))

		try:
			self.handle_page_visit()
		except Exception as error:
			self.server.logger.error('handle_page_visit raised error: ' + error.__class__.__name__)

		self.end_headers()
		self.wfile.write(template_data.encode('utf-8', 'ignore'))
		return

	def _respond_file_raw(self, file_path, attachment):
		try:
			file_obj = open(file_path, 'rb')
		except IOError:
			raise KingPhisherErrorAbortRequest()
		fs = os.fstat(file_obj.fileno())
		self.send_response(200)
		self.send_header('Content-Type', self.guess_mime_type(file_path))
		self.send_header('Content-Length', str(fs[6]))
		if attachment:
			file_name = os.path.basename(file_path)
			self.send_header('Content-Disposition', 'attachment; filename=' + file_name)
		self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
		self.end_headers()
		shutil.copyfileobj(file_obj, self.wfile)
		file_obj.close()
		return

	def _respond_file_check_id(self):
		if not self.config.get('server.require_id'):
			return
		if self.message_id == self.config.get('server.secret_id'):
			return
		# a valid campaign_id requires a valid message_id
		if not self.campaign_id:
			self.server.logger.warning('denying request due to lack of a valid id')
			raise KingPhisherErrorAbortRequest()
		if self.query_count('SELECT COUNT(id) FROM landing_pages WHERE campaign_id = ? AND hostname = ?', (self.campaign_id, self.vhost)) == 0:
			self.server.logger.warning('denying request with not found due to invalid hostname')
			raise KingPhisherErrorAbortRequest()
		with self.get_cursor() as cursor:
			cursor.execute('SELECT reject_after_credentials FROM campaigns WHERE id = ?', (self.campaign_id,))
			reject_after_credentials = cursor.fetchone()[0]
		if reject_after_credentials and self.visit_id == None and self.query_count('SELECT COUNT(id) FROM credentials WHERE message_id = ?', (self.message_id,)):
			self.server.logger.warning('denying request because credentials were already harvested')
			raise KingPhisherErrorAbortRequest()
		return

	def respond_not_found(self):
		self.send_response(404, 'Resource Not Found')
		self.send_header('Content-Type', 'text/html')
		self.end_headers()
		page_404 = find.find_data_file('error_404.html')
		if page_404:
			shutil.copyfileobj(open(page_404), self.wfile)
		else:
			self.wfile.write('Resource Not Found\n')
		return

	def respond_redirect(self, location='/'):
		location = location.lstrip('/')
		if self.config.get('server.vhost_directories') and location.startswith(self.vhost):
			location = location[len(self.vhost):]
		if not location.startswith('/'):
			location = '/' + location
		super(KingPhisherRequestHandler, self).respond_redirect(location)

	def handle_deaddrop_visit(self, query):
		self.send_response(200)
		self.end_headers()

		data = self.get_query_parameter('token')
		if not data:
			self.logger.warning('dead drop request received with no \'token\' parameter')
			return
		try:
			data = data.decode('base64')
		except binascii.Error:
			self.logger.error('dead drop request received with invalid \'token\' data')
			return
		data = xor.xor_decode(data)
		try:
			data = json.loads(data)
		except ValueError:
			self.logger.error('dead drop request received with invalid \'token\' data')
			return

		deployment_id = data.get('deaddrop_id')
		with self.get_cursor() as cursor:
			cursor.execute('SELECT campaign_id FROM deaddrop_deployments WHERE id = ?', (deployment_id,))
			campaign_id = cursor.fetchone()
			if not campaign_id:
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
			return
			values = (deployment_id, campaign_id, self.client_address[0], local_username, local_hostname, local_ip_addresses)
			cursor.execute('INSERT INTO deaddrop_connections (deployment_id, campaign_id, visitor_ip, local_username, local_hostname, local_ip_addresses) VALUES (?, ?, ?, ?, ?, ?)', values)

		visit_count = self.query_count('SELECT COUNT(id) FROM deaddrop_connections WHERE campaign_id = ?', (campaign_id,))
		if visit_count > 0 and ((visit_count in [1, 3, 5]) or ((visit_count % 10) == 0)):
			alert_text = "{0} deaddrop connections reached for campaign: {{campaign_name}}".format(visit_count)
			self.server.job_manager.job_run(self.issue_alert, (alert_text, campaign_id))
		return

	def handle_email_opened(self, query):
		# image size: 49 Bytes
		img_data = '47494638396101000100910000000000ffffffffffff00000021f90401000002'
		img_data += '002c00000000010001000002025401003b'
		img_data = img_data.decode('hex')
		self.send_response(200)
		self.send_header('Content-Type', 'image/gif')
		self.send_header('Content-Length', str(len(img_data)))
		self.end_headers()
		self.wfile.write(img_data)

		msg_id = self.get_query_parameter('id')
		if not msg_id:
			return
		with self.get_cursor() as cursor:
			cursor.execute('UPDATE messages SET opened = CURRENT_TIMESTAMP WHERE id = ? AND opened IS NULL', (msg_id,))

	def handle_javascript_hook(self, query):
		kp_hook_js = find.find_data_file('javascript_hook.js')
		if not kp_hook_js:
			self.respond_not_found()
			return
		javascript = open(kp_hook_js).read()
		if self.config.has_option('beef.hook_url'):
			javascript += "\nloadScript('{0}');\n\n".format(self.config.get('beef.hook_url'))
		self.send_response(200)
		self.send_header('Content-Type', 'text/javascript')
		self.send_header('Pragma', 'no-cache')
		self.send_header('Cache-Control', 'no-cache')
		self.send_header('Expires', '0')
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Methods', 'POST, GET')
		self.send_header('Content-Length', str(len(javascript)))
		self.end_headers()
		self.wfile.write(javascript)
		return

	def handle_page_visit(self):
		if not self.message_id:
			return
		if not self.campaign_id:
			return
		message_id = self.message_id
		campaign_id = self.campaign_id
		with self.get_cursor() as cursor:
			# set the opened timestamp to the visit time if it's null
			cursor.execute('UPDATE messages SET opened = CURRENT_TIMESTAMP WHERE id = ? AND opened IS NULL', (self.message_id,))

		if self.visit_id == None:
			visit_id = make_uid()
			kp_cookie_name = self.config.get('server.cookie_name')
			cookie = "{0}={1}; Path=/; HttpOnly".format(kp_cookie_name, visit_id)
			self.send_header('Set-Cookie', cookie)
			with self.get_cursor() as cursor:
				client_ip = self.client_address[0]
				user_agent = (self.headers.getheader('user-agent') or '')
				cursor.execute('INSERT INTO visits (id, message_id, campaign_id, visitor_ip, visitor_details) VALUES (?, ?, ?, ?, ?)', (visit_id, message_id, campaign_id, client_ip, user_agent))
				visit_count = self.query_count('SELECT COUNT(id) FROM visits WHERE campaign_id = ?', (campaign_id,))
			if visit_count > 0 and ((visit_count in [1, 10, 25]) or ((visit_count % 50) == 0)):
				alert_text = "{0} vists reached for campaign: {{campaign_name}}".format(visit_count)
				self.server.job_manager.job_run(self.issue_alert, (alert_text, campaign_id))
		else:
			visit_id = self.visit_id
			if self.query_count('SELECT COUNT(id) FROM landing_pages WHERE campaign_id = ? AND hostname = ? AND page = ?', (self.campaign_id, self.vhost, self.path)):
				with self.get_cursor() as cursor:
					cursor.execute('UPDATE visits SET visit_count = visit_count + 1, last_visit = CURRENT_TIMESTAMP WHERE id = ?', (visit_id,))

		username = None
		for pname in ['username', 'user', 'u']:
			username = (self.get_query_parameter(pname) or self.get_query_parameter(pname.title()) or self.get_query_parameter(pname.upper()))
			if username:
				break
		if username:
			password = None
			for pname in ['password', 'pass', 'p']:
				password = (self.get_query_parameter(pname) or self.get_query_parameter(pname.title()) or self.get_query_parameter(pname.upper()))
				if password:
					break
			password = (password or '')
			cred_count = 0
			with self.get_cursor() as cursor:
				cursor.execute('SELECT COUNT(id) FROM credentials WHERE message_id = ? AND username = ? AND password = ?', (message_id, username, password))
				if cursor.fetchone()[0] == 0:
					cursor.execute('INSERT INTO credentials (visit_id, message_id, campaign_id, username, password) VALUES (?, ?, ?, ?, ?)', (visit_id, message_id, campaign_id, username, password))
					cred_count = self.query_count('SELECT COUNT(id) FROM credentials WHERE campaign_id = ?', (campaign_id,))
			if cred_count > 0 and ((cred_count in [1, 5, 10]) or ((cred_count % 25) == 0)):
				alert_text = "{0} credentials submitted for campaign: {{campaign_name}}".format(cred_count)
				self.server.job_manager.job_run(self.issue_alert, (alert_text, campaign_id))

		trained = self.get_query_parameter('trained')
		if isinstance(trained, (str, unicode)) and trained.lower() in ['1', 'true', 'yes']:
			with self.get_cursor() as cursor:
				cursor.execute('UPDATE messages SET trained = 1 WHERE id = ?', (message_id,))

class KingPhisherServer(AdvancedHTTPServer):
	"""
	The main HTTP and RPC server for King Phisher.
	"""
	def __init__(self, config, *args, **kwargs):
		"""
		:param config: Configuration to retrieve settings from.
		:type config: :py:class:`.Configuration`
		"""
		self.logger = logging.getLogger('KingPhisher.Server')
		super(KingPhisherServer, self).__init__(*args, **kwargs)
		self.config = config
		"""The main King Phisher server configuration."""
		self.serve_files = True
		self.serve_files_root = config.get('server.web_root')
		self.serve_files_list_directories = False
		self.serve_robots_txt = True
		self.init_database(config.get('server.database'))

		self.http_server.config = config
		self.http_server.throttle_semaphore = threading.Semaphore()
		self.http_server.forked_authenticator = authenticator.ForkedAuthenticator()
		self.logger.debug('forked an authenticating process with PID: ' + str(self.http_server.forked_authenticator.child_pid))
		self.job_manager = job.JobManager()
		"""A :py:class:`.JobManager` instance for scheduling tasks."""
		self.job_manager.start()
		self.http_server.job_manager = self.job_manager
		loader = jinja2.FileSystemLoader(config.get('server.web_root'))
		global_vars = None
		if config.has_section('server.page_variables'):
			global_vars = config.get('server.page_variables')
		self.http_server.template_env = templates.KingPhisherTemplateEnvironment(loader=loader, global_vars=global_vars)

		self.__is_shutdown = threading.Event()
		self.__is_shutdown.clear()

	def init_database(self, database_file):
		"""
		Initialize the servers database connection, creating a new one
		if the file does not exist.

		:param str database_file: The SQLite3 database file to use.
		"""
		if not os.path.exists(database_file) or database_file == ':memory:':
			db = database.create_database(database_file)
			self.logger.info('created new sqlite3 database file')
		else:
			db = database.KingPhisherDatabase(database_file)
		self.logger.debug("loaded database: {0} schema version: {1}".format(database_file, db.schema_version))
		self.database = db
		self.http_server.database = db

	def shutdown(self, *args, **kwargs):
		"""
		Request that the server perform any cleanup necessary and then
		shut down. This will wait for the server to stop before it
		returns.
		"""
		if self.__is_shutdown.is_set():
			return
		self.logger.warning('processing shutdown request')
		super(KingPhisherServer, self).shutdown(*args, **kwargs)
		self.http_server.forked_authenticator.stop()
		self.logger.debug('stopped the forked authenticator process')
		self.job_manager.stop()
		self.__is_shutdown.set()
