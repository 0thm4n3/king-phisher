#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/mailer.py
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

import csv
import logging
import mimetypes
import ipaddress
import os
import random
import smtplib
import socket
import sys
import threading
import time

from king_phisher import templates
from king_phisher import utilities
from king_phisher.client import gui_utilities
from king_phisher.ssh_forward import SSHTCPForwarder

from gi.repository import GLib

if sys.version_info[0] < 3:
	from email import Encoders as encoders
	import urllib
	import urlparse
	urllib.parse = urlparse
	from email.MIMEBase import MIMEBase
	from email.MIMEImage import MIMEImage
	from email.MIMEMultipart import MIMEMultipart
	from email.MIMEText import MIMEText
else:
	from email import encoders
	import urllib.parse
	from email.mime.base import MIMEBase
	from email.mime.image import MIMEImage
	from email.mime.multipart import MIMEMultipart
	from email.mime.text import MIMEText

__all__ = ['format_message', 'guess_smtp_server_address', 'MailSenderThread']

make_uid = lambda: utilities.random_string(16)
template_environment = templates.MessageTemplateEnvironment()

def format_message(template, config, first_name=None, last_name=None, uid=None, target_email=None):
	"""
	Take a message from a template and format it to be sent by replacing
	variables and processing other template directives. If the *uid* parameter
	is not set, then the message is formatted to be previewed.

	:param str template: The message template.
	:param dict config: The King Phisher client configuration.
	:param str first_name: The first name of the message's recipient.
	:param str last_name: The last name of the message's recipient.
	:param str uid: The messages unique identifier.
	:param str target_email: The message's destination email address.
	:return: The formatted message.
	:rtype: str
	"""
	if uid == None:
		template_environment.set_mode(template_environment.MODE_PREVIEW)
	first_name = ('Alice' if not isinstance(first_name, str) else first_name)
	last_name = ('Liddle' if not isinstance(last_name, str) else last_name)
	target_email = ('aliddle@wonderland.com' if not isinstance(target_email, str) else target_email)
	uid = (uid or config['server_config'].get('server.secret_id') or make_uid())

	template = template_environment.from_string(template)
	template_vars = {}
	template_client_vars = {}

	template_client_vars['first_name'] = first_name
	template_client_vars['last_name'] = last_name
	template_client_vars['email_address'] = target_email
	template_client_vars['company_name'] = config.get('mailer.company_name', 'Wonderland Inc.')
	template_client_vars['message_id'] = uid

	template_vars['client'] = template_client_vars
	template_vars['uid'] = uid

	webserver_url = config.get('mailer.webserver_url', '')
	webserver_url = urlparse.urlparse(webserver_url)
	tracking_image = config['server_config']['server.tracking_image']
	template_vars['webserver'] = webserver_url.netloc
	tracking_url = urlparse.urlunparse((webserver_url.scheme, webserver_url.netloc, tracking_image, '', 'id=' + uid, ''))
	webserver_url = urlparse.urlunparse((webserver_url.scheme, webserver_url.netloc, webserver_url.path, '', '', ''))
	template_vars['tracking_dot_image_tag'] = "<img src=\"{0}\" style=\"display:none\" />".format(tracking_url)

	template_vars_url = {}
	template_vars_url['rickroll'] = 'http://www.youtube.com/watch?v=oHg5SJYRHA0'
	template_vars_url['webserver'] = webserver_url + '?id=' + uid
	template_vars_url['webserver_raw'] = webserver_url
	template_vars_url['tracking_dot'] = tracking_url
	template_vars['url'] = template_vars_url
	template_vars.update(template_environment.standard_variables)
	return template.render(template_vars)

def guess_smtp_server_address(host, forward_host=None):
	"""
	Guess the IP address of the SMTP server that will be connected to given the
	SMTP host information and an optional SSH forwarding host. If a hostname is
	in use it will be resolved to an IP address, either IPv4 or IPv6 and in that
	order. If a hostname resolves to multiple IP addresses, None will be
	returned. This function is intended to guess the SMTP servers IP address
	given the client configuration so it can be used for SPF record checks.

	:param str host: The SMTP server that is being connected to.
	:param str forward_host: An optional host that is being used to tunnel the connection.
	:return: The ip address of the SMTP server.
	:rtype: None, :py:class:`ipaddress.IPv4Address`, :py:class:`ipaddress.IPv6Address`
	"""
	host = host.rsplit(':', 1)[0]
	if utilities.is_valid_ip_address(host):
		ip = ipaddress.ip_address(host)
		if not ip.is_loopback:
			return ip
	else:
		info = None
		for family in (socket.AF_INET, socket.AF_INET6):
			try:
				info = socket.getaddrinfo(host, 1, family)
			except socket.gaierror:
				continue
			info = set(list(map(lambda r: r[4][0], info)))
			if len(info) != 1:
				return
			break
		if info:
			ip = ipaddress.ip_address(info.pop())
			if not ip.is_loopback:
				return ip
	if forward_host:
		return guess_smtp_server_address(forward_host)
	return

class MailSenderThread(threading.Thread):
	"""
	The King Phisher threaded email message sender. This object manages
	the sending of emails for campaigns and supports pausing the sending of
	messages which can later be resumed by unpausing. This object reports
	its information to the GUI through an optional
	:py:class:`.MailSenderSendTab` instance, these two objects
	are very interdependent.
	"""
	def __init__(self, config, target_file, rpc, tab=None):
		"""
		:param dict config: The King Phisher client configuration.
		:param str target_file: The CSV formatted file to read message targets from.
		:param tab: The GUI tab to report information to.
		:type tab: :py:class:`.MailSenderSendTab`
		:param rpc: The client's connected RPC instance.
		:type rpc: :py:class:`.KingPhisherRPCClient`
		"""
		super(MailSenderThread, self).__init__()
		self.daemon = True
		self.logger = logging.getLogger('KingPhisher.Client.' + self.__class__.__name__)
		self.config = config
		self.target_file = target_file
		"""The name of the target file in CSV format."""
		self.tab = tab
		"""The optional :py:class:`.MailSenderSendTab` instance for reporting status messages to the GUI."""
		self.rpc = rpc
		self.ssh_forwarder = None
		"""The :py:class:`.SSHTCPForwarder` instance for tunneling traffic to the SMTP server."""
		self.smtp_connection = None
		"""The :py:class:`smtplib.SMTP` connection instance."""
		self.smtp_server = utilities.server_parse(self.config['smtp_server'], 25)
		self.running = threading.Event()
		"""A :py:class:`threading.Event` object indicating if emails are being sent."""
		self.paused = threading.Event()
		"""A :py:class:`threading.Event` object indicating if the email sending operation is or should be paused."""
		self.should_exit = threading.Event()
		self.max_messages_per_minute = float(self.config.get('smtp_max_send_rate', 0.0))
		self._mime_attachments = None

	def tab_notify_sent(self, emails_done, emails_total):
		"""
		Notify the tab that messages have been sent.

		:param int emails_done: The number of emails that have been sent.
		:param int emails_total: The total number of emails that are going to be sent.
		"""
		if isinstance(self.tab, gui_utilities.UtilityGladeGObject):
			GLib.idle_add(lambda x: self.tab.notify_sent(*x), (emails_done, emails_total))

	def tab_notify_status(self, message):
		"""
		Handle a status message regarding the message sending operation.

		:param str message: The notification message.
		"""
		self.logger.info(message.lower())
		if isinstance(self.tab, gui_utilities.UtilityGladeGObject):
			GLib.idle_add(self.tab.notify_status, message + '\n')

	def tab_notify_stopped(self):
		"""
		Notify the tab that the message sending operation has stopped.
		"""
		if isinstance(self.tab, gui_utilities.UtilityGladeGObject):
			GLib.idle_add(self.tab.notify_stopped)

	def server_ssh_connect(self):
		"""
		Connect to the remote SMTP server over SSH and configure port
		forwarding with :py:class:`.SSHTCPForwarder` for tunneling SMTP
		traffic.

		:return: The connection status.
		:rtype: bool
		"""
		server = utilities.server_parse(self.config['ssh_server'], 22)
		username = self.config['ssh_username']
		password = self.config['ssh_password']
		remote_server = utilities.server_parse(self.config['smtp_server'], 25)
		local_port = random.randint(2000, 6000)
		try:
			self.ssh_forwarder = SSHTCPForwarder(server, username, password, local_port, remote_server, preferred_private_key=self.config.get('ssh_preferred_key'))
			self.ssh_forwarder.start()
			time.sleep(0.5)
		except:
			self.logger.warning('failed to connect to remote ssh server')
			return False
		self.smtp_server = ('localhost', local_port)
		return True

	def server_smtp_connect(self):
		"""
		Connect to the configured SMTP server.

		:return: The connection status.
		:rtype: bool
		"""
		if self.config.get('smtp_ssl_enable', False):
			SMTP_CLASS = smtplib.SMTP_SSL
		else:
			SMTP_CLASS = smtplib.SMTP
		try:
			self.smtp_connection = SMTP_CLASS(*self.smtp_server)
		except:
			return False
		return True

	def server_smtp_disconnect(self):
		"""Clean up and close the connection to the remote SMTP server."""
		if self.smtp_connection:
			try:
				self.smtp_connection.quit()
			except smtplib.SMTPServerDisconnected:
				pass
			self.smtp_connection = None
			self.tab_notify_status('Disconnected from the SMTP server')

	def server_smtp_reconnect(self):
		"""
		Disconnect from the remote SMTP server and then attempt to open
		a new connection to it.

		:return: The reconnection status.
		:rtype: bool
		"""
		if self.smtp_connection:
			try:
				self.smtp_connection.quit()
			except smtplib.SMTPServerDisconnected:
				pass
			self.smtp_connection = None
		while not self.server_smtp_connect():
			self.tab_notify_status('Failed to reconnect to the SMTP server')
			if not self.process_pause(True):
				return False
		return True

	def count_emails(self):
		"""
		Count the emails contained in the target CSV file.

		:return: The number of targets in the file.
		:rtype: int
		"""
		targets = 0
		target_file_h = open(self.target_file, 'r')
		csv_reader = csv.DictReader(target_file_h, ['first_name', 'last_name', 'email_address'])
		for target in csv_reader:
			if not utilities.is_valid_email_address(target['email_address']):
				continue
			targets += 1
		target_file_h.close()
		return targets

	def run(self):
		emails_done = 0
		emails_total = self.count_emails()
		max_messages_per_connection = self.config.get('mailer.max_messages_per_connection', 5)
		self.running.set()
		self.should_exit.clear()
		self.paused.clear()
		self._prepare_env()

		self._mime_attachments = self._get_mime_attachments()
		self.logger.debug("loaded {0:,} MIME attachments".format(len(self._mime_attachments)))

		target_file_h = open(self.target_file, 'r')
		csv_reader = csv.DictReader(target_file_h, ['first_name', 'last_name', 'email_address'])
		for target in csv_reader:
			if not utilities.is_valid_email_address(target['email_address']):
				self.logger.warning('skipping invalid email address: ' + target['email_address'])
				continue
			iteration_time = time.time()
			if self.should_exit.is_set():
				self.tab_notify_status('Sending emails cancelled')
				break
			if not self.process_pause():
				break
			if emails_done > 0 and (emails_done % max_messages_per_connection):
				self.server_smtp_reconnect()

			uid = make_uid()
			emails_done += 1
			self.tab_notify_status("Sending email {0:,} of {1:,} to {2} with UID: {3}".format(emails_done, emails_total, target['email_address'], uid))
			msg = self.create_email(target['first_name'], target['last_name'], target['email_address'], uid)
			if not self._try_send_email(target['email_address'], msg):
				break

			self.tab_notify_sent(emails_done, emails_total)
			campaign_id = self.config['campaign_id']
			company_name = self.config.get('mailer.company_name', '')
			self.rpc('campaign/message/new', campaign_id, uid, target['email_address'], company_name, target['first_name'], target['last_name'])

			if self.max_messages_per_minute:
				iteration_time = (time.time() - iteration_time)
				sleep_time = (60.0 / float(self.max_messages_per_minute)) - iteration_time
				while sleep_time > 0:
					sleep_chunk = min(sleep_time, 0.5)
					time.sleep(sleep_chunk)
					if self.should_exit.is_set():
						break
					sleep_time -= sleep_chunk

		target_file_h.close()
		self._mime_attachments = None

		self.tab_notify_status("Finished sending emails, successfully sent {0:,} emails".format(emails_done))
		self.server_smtp_disconnect()
		if self.ssh_forwarder:
			self.ssh_forwarder.stop()
			self.ssh_forwarder = None
			self.tab_notify_status('Disconnected from the SSH server')
		self.tab_notify_stopped()
		return

	def process_pause(self, set_pause=False):
		"""
		Pause sending emails if a pause request has been set.

		:param bool set_pause: Whether to request a pause before processing it.
		:return: Whether or not the sending operation was cancelled during the pause.
		:rtype: bool
		"""
		if set_pause:
			if isinstance(self.tab, gui_utilities.UtilityGladeGObject):
				gui_utilities.glib_idle_add_wait(lambda: self.tab.pause_button.set_property('active', True))
			else:
				self.pause()
		if self.paused.is_set():
			self.tab_notify_status('Paused sending emails, waiting to resume')
			self.running.wait()
			self.paused.clear()
			if self.should_exit.is_set():
				self.tab_notify_status('Sending emails cancelled')
				return False
			self.tab_notify_status('Resuming sending emails')
			self.max_messages_per_minute = float(self.config.get('smtp_max_send_rate', 0.0))
		return True

	def create_email(self, first_name, last_name, target_email, uid):
		"""
		Create a MIME email to be sent from a set of parameters.

		:param str first_name: The first name of the message's recipient.
		:param str last_name: The last name of the message's recipient.
		:param str target_email: The message's destination email address.
		:param str uid: The message's unique identifier.
		:return: The new MIME message.
		:rtype: :py:class:`email.MIMEMultipart.MIMEMultipart`
		"""
		msg = MIMEMultipart()
		msg['Subject'] = self.config['mailer.subject']
		if self.config.get('mailer.reply_to_email'):
			msg.add_header('reply-to', self.config['mailer.reply_to_email'])
		if self.config.get('mailer.source_email_alias'):
			msg['From'] = "\"{0}\" <{1}>".format(self.config['mailer.source_email_alias'], self.config['mailer.source_email'])
		else:
			msg['From'] = self.config['mailer.source_email']
		msg['To'] = target_email
		importance = self.config.get('mailer.importance', 'Normal')
		if importance != 'Normal':
			msg['Importance'] = importance
		sensitivity = self.config.get('mailer.sensitivity', 'Normal')
		if sensitivity != 'Normal':
			msg['Sensitivity'] = sensitivity
		msg.preamble = 'This is a multi-part message in MIME format.'
		msg_alt = MIMEMultipart('alternative')
		msg.attach(msg_alt)
		msg_template = open(self.config['mailer.html_file'], 'r').read()
		formatted_msg = format_message(msg_template, self.config, first_name=first_name, last_name=last_name, uid=uid, target_email=target_email)
		msg_body = MIMEText(formatted_msg, "html")
		msg_alt.attach(msg_body)

		# process attachments
		if isinstance(self._mime_attachments, (list, tuple)):
			attachfiles = self._mime_attachments
		else:
			attachfiles = self._get_mime_attachments()
		for attachfile in attachfiles:
			msg.attach(attachfile)
		return msg

	def _get_mime_attachments(self):
		attachments = []
		if self.config.get('mailer.attachment_file'):
			attachment = self.config['mailer.attachment_file']
			attachfile = MIMEBase(*mimetypes.guess_type(attachment))
			attachfile.set_payload(open(attachment, 'rb').read())
			encoders.encode_base64(attachfile)
			attachfile.add_header('Content-Disposition', "attachment; filename=\"{0}\"".format(os.path.basename(attachment)))
			attachments.append(attachfile)
		for attachment_file, attachment_name in template_environment.attachment_images.items():
			attachfile = MIMEImage(open(attachment_file, 'rb').read())
			attachfile.add_header('Content-ID', "<{0}>".format(attachment_name))
			attachfile.add_header('Content-Disposition', "inline; filename=\"{0}\"".format(attachment_name))
			attachments.append(attachfile)
		return attachments

	def _prepare_env(self):
		msg_template = open(self.config['mailer.html_file'], 'r').read()
		template_environment.set_mode(template_environment.MODE_ANALYZE)
		format_message(msg_template, self.config, uid=make_uid())
		template_environment.set_mode(template_environment.MODE_SEND)

	def _try_send_email(self, *args, **kwargs):
		message_sent = False
		while not message_sent:
			for i in xrange(0, 3):
				try:
					self.send_email(*args, **kwargs)
					message_sent = True
					break
				except:
					self.tab_notify_status('Failed to send message')
					time.sleep(1)
			if not message_sent:
				self.server_smtp_disconnect()
				if not self.process_pause(True):
					return False
				self.server_smtp_reconnect()
		return True

	def send_email(self, target_email, msg):
		"""
		Send an email using the connected SMTP server.

		:param str target_email: The email address to send the message to.
		:param msg: The formatted message to be sent.
		:type msg: :py:class:`email.MIMEMultipart.MIMEMultipart`
		"""
		source_email = self.config['mailer.source_email']
		self.smtp_connection.sendmail(source_email, target_email, msg.as_string())

	def pause(self):
		"""
		Sets the :py:attr:`~.MailSenderThread.running` and
		:py:attr:`~.MailSenderThread.paused` flags correctly to indicate
		that the object is paused.
		"""
		self.running.clear()
		self.paused.set()

	def unpause(self):
		"""
		Sets the :py:attr:`~.MailSenderThread.running` and
		:py:attr:`~.MailSenderThread.paused` flags correctly to indicate
		that the object is no longer paused.
		"""
		self.running.set()

	def stop(self):
		"""
		Requests that the email sending operation stop. It can not be
		resumed from the same position. This function blocks until the
		stop request has been processed and the thread exits.
		"""
		self.should_exit.set()
		self.unpause()
		if self.is_alive():
			self.join()

	def missing_files(self):
		"""
		Return a list of all missing or unreadable files which are referenced by
		the message template.

		:return: The list of unusable files.
		:rtype: list
		"""
		missing = []
		attachment = self.config.get('mailer.attachment_file')
		if attachment and not os.access(attachment, os.R_OK):
			missing.append(attachment)
		msg_template = self.config['mailer.html_file']
		if not os.access(msg_template, os.R_OK):
			missing.append(msg_template)
			return missing
		self._prepare_env()
		missing.extend(filter(lambda f: not os.access(f, os.R_OK), template_environment.attachment_images.keys()))
		return missing
