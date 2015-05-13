#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/tabs/mail.py
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
import os
import socket
import sys
import urllib

from king_phisher import spf
from king_phisher import utilities
from king_phisher.client import dialogs
from king_phisher.client import export
from king_phisher.client import gui_utilities
from king_phisher.client import mailer
from king_phisher.constants import SPFResult
from king_phisher.errors import KingPhisherInputValidationError

from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Pango

if sys.version_info[0] < 3:
	import urllib2
	import urlparse
	urllib.parse = urlparse
	urllib.parse.urlencode = urllib.urlencode
	urllib.request = urllib2
else:
	import urllib.parse
	import urllib.request

try:
	from gi.repository import WebKit2 as WebKitX
	has_webkit2 = True
except ImportError:
	from gi.repository import WebKit as WebKitX
	has_webkit2 = False

def test_webserver_url(target_url, secret_id):
	"""
	Test the target URL to ensure that it is valid and the server is responding.

	:param str target_url: The URL to make a test request to.
	:param str secret_id: The King Phisher Server secret id to include in the test request.
	"""
	parsed_url = urllib.parse.urlparse(target_url)
	query = urllib.parse.parse_qs(parsed_url.query)
	query['id'] = [secret_id]
	query = urllib.parse.urlencode(query, True)
	target_url = urllib.parse.urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, query, parsed_url.fragment))
	urllib.request.urlopen(target_url, timeout=5)

class MailSenderSendTab(gui_utilities.GladeGObject):
	"""
	This allows the :py:class:`.MailSenderThread` object to be managed
	by the user through the GUI. These two classes are very interdependent
	"""
	gobject_ids = [
		'button_mail_sender_start',
		'button_mail_sender_stop',
		'textview_mail_sender_progress',
		'togglebutton_mail_sender_pause',
		'progressbar_mail_sender',
		'scrolledwindow_mail_sender_progress'
	]
	top_gobject = 'box'
	def __init__(self, *args, **kwargs):
		self.label = Gtk.Label(label='Send')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderSendTab, self).__init__(*args, **kwargs)
		self.textview = self.gobjects['textview_mail_sender_progress']
		"""The :py:class:`Gtk.TextView` object that renders text status messages."""
		self.textview.modify_font(Pango.FontDescription(self.config['text_font']))
		self.textbuffer = self.textview.get_buffer()
		"""The :py:class:`Gtk.TextBuffer` instance associated with :py:attr:`~.MailSenderSendTab.textview`."""
		self.textbuffer_iter = self.textbuffer.get_start_iter()
		self.progressbar = self.gobjects['progressbar_mail_sender']
		"""The :py:class:`Gtk.ProgressBar` instance which is used to display progress of sending messages."""
		self.pause_button = self.gobjects['togglebutton_mail_sender_pause']
		self.sender_thread = None
		"""The :py:class:`.MailSenderThread` instance that is being used to send messages."""
		self.parent.connect('exit', self.signal_kpc_exit)
		self.parent.connect('exit-confirm', self.signal_kpc_exit_confirm)
		self.textview.connect('populate-popup', self.signal_textview_populate_popup)

	def _sender_precheck_settings(self):
		required_settings = {
			'mailer.webserver_url': 'Web Server URL',
			'mailer.company_name': 'Company Name',
			'mailer.subject': 'Subject',
			'mailer.html_file': 'Message HTML File',
			'mailer.target_file': 'Target CSV File'
		}
		for setting, setting_name in required_settings.items():
			if not self.config.get(setting):
				gui_utilities.show_dialog_warning("Missing Required Option: '{0}'".format(setting_name), self.parent, 'Return to the Config tab and set all required options')
				return
			if not setting.endswith('_file'):
				continue
			file_path = self.config[setting]
			if not (os.path.isfile(file_path) and os.access(file_path, os.R_OK)):
				gui_utilities.show_dialog_warning('Invalid Option Configuration', self.parent, "Setting: '{0}'\nReason: the file could not be read.".format(setting_name))
				return False
		if not self.config.get('smtp_server'):
			gui_utilities.show_dialog_warning('Missing SMTP Server Setting', self.parent, 'Please configure the SMTP server')
			return False
		return True

	def _sender_precheck_source(self):
		valid = utilities.is_valid_email_address(self.config['mailer.source_email'])
		valid = valid and utilities.is_valid_email_address(self.config['mailer.source_email_smtp'])
		if valid:
			return True
		self.text_insert('WARNING: One or more source email addresses specified are invalid.\n')
		if not gui_utilities.show_dialog_yes_no('Invalid Email Address', self.parent, 'One or more source email addresses specified are invalid.\nContinue sending messages anyways?'):
			self.text_insert('Sending aborted due to invalid source email address.\n')
			return False
		return True

	def _sender_precheck_spf(self):
		spf_check_level = self.config['spf_check_level']
		if not spf_check_level:
			return True
		if not utilities.is_valid_email_address(self.config['mailer.source_email_smtp']):
			self.text_insert('WARNING: Can not check SPF records for an invalid source email address.\n')
			return True

		spf_test_ip = mailer.guess_smtp_server_address(self.config['smtp_server'], (self.config['ssh_server'] if self.config['smtp_ssh_enable'] else None))
		if not spf_test_ip:
			self.text_insert('Skipped checking the SPF policy because the SMTP server address could not be detected.\n')
			self.logger.warning('skipping spf policy check because the smtp server address could not be reliably detected')
			return True

		self.logger.debug('detected the smtp server address as ' + str(spf_test_ip))
		spf_test_sender, spf_test_domain = self.config['mailer.source_email_smtp'].split('@')
		self.text_insert("Checking the SPF policy of target domain '{0}'... ".format(spf_test_domain))
		try:
			spf_test = spf.SenderPolicyFramework(spf_test_ip, spf_test_domain, spf_test_sender)
			spf_result = spf_test.check_host()
		except spf.SPFError as error:
			self.text_insert("done, encountered exception: {0}.\n".format(error.__class__.__name__))
			return True

		if not spf_result:
			self.text_insert('done, no policy was found.\n')
		else:
			self.text_insert('done.\n')
		dialog_title = 'Sender Policy Framework Failure'
		dialog_message = None
		if spf_check_level == 1 and spf_result in [SPFResult.FAIL, SPFResult.SOFT_FAIL]:
			dialog_message = 'The configuration fails the domains SPF policy.\nMessages may be marked as forged.'
		elif spf_check_level == 2 and not spf_result in [SPFResult.NEUTRAL, SPFResult.PASS]:
			dialog_message = 'The configuration does not pass the domains SPF policy.'
		spf_result = spf_result or 'N/A (No policy found)'
		self.text_insert("{0}SPF policy result: {1}\n".format(('WARNING: ' if spf_result.endswith('fail') else ''), spf_result))
		if dialog_message:
			dialog_message += '\n\nContinue sending messages anyways?'
			if not gui_utilities.show_dialog_yes_no(dialog_title, self.parent, dialog_message):
				self.text_insert('Sending aborted due to the SPF policy.\n')
				return False
		return True

	def _sender_precheck_url(self):
		self.text_insert('Checking the target URL... ')
		try:
			test_webserver_url(self.config['mailer.webserver_url'], self.config['server_config']['server.secret_id'])
		except Exception:
			self.text_insert('failed')
			if not gui_utilities.show_dialog_yes_no('Unable To Open The Web Server URL', self.parent, 'The URL may be invalid, continue sending messages anyways?'):
				self.text_insert(', sending aborted.\n')
				return
			self.text_insert(', error ignored.\n')
		else:
			self.text_insert('success, done.\n')
		return True

	def signal_activate_popup_menu_clear_all(self, widget):
		self.textbuffer.delete(self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter())
		self.textbuffer_iter = self.textbuffer.get_start_iter()

	def signal_button_clicked_sender_start(self, button):
		if not self._sender_precheck_settings():
			return
		if not self._sender_precheck_url():
			return
		if not self._sender_precheck_source():
			return
		if not self._sender_precheck_spf():
			return

		# after this the operation needs to call self.sender_start_failure to quit
		if self.sender_thread:
			return
		# _FIXME: change this to app
		#self.parent.save_config()
		self.gobjects['button_mail_sender_start'].set_sensitive(False)
		self.gobjects['button_mail_sender_stop'].set_sensitive(True)
		self.progressbar.set_fraction(0)
		self.sender_thread = mailer.MailSenderThread(self.config, self.config['mailer.target_file'], self.parent.rpc, self)

		# verify settings
		missing_files = self.sender_thread.missing_files()
		if missing_files:
			text = ''.join("Missing required file: '{0}'\n".format(f) for f in missing_files)
			self.sender_start_failure('Missing required files', text)
			return

		# connect to the smtp server
		if self.config['smtp_ssh_enable']:
			while True:
				self.text_insert('Connecting to SSH... ')
				login_dialog = dialogs.SSHLoginDialog(self.config, self.parent)
				login_dialog.objects_load_from_config()
				response = login_dialog.interact()
				if response != Gtk.ResponseType.APPLY:
					self.sender_start_failure(text='canceled.\n')
					return
				if self.sender_thread.server_ssh_connect():
					self.text_insert('done.\n')
					break
				self.sender_start_failure(('Connection Failed', 'Failed to connect to the SSH server.'), 'failed.\n', retry=True)
		self.text_insert('Connecting to SMTP server... ')
		if not self.sender_thread.server_smtp_connect():
			self.sender_start_failure(('Connection Failed', 'Failed to connect to the SMTP server.'), 'failed.\n')
			return
		self.text_insert('done.\n')

		parsed_target_url = urllib.parse.urlparse(self.config['mailer.webserver_url'])
		landing_page_hostname = parsed_target_url.netloc
		landing_page = parsed_target_url.path
		landing_page = landing_page.lstrip('/')
		self.parent.rpc('campaign/landing_page/new', self.config['campaign_id'], landing_page_hostname, landing_page)

		self.sender_thread.start()
		self.gobjects['togglebutton_mail_sender_pause'].set_sensitive(True)

	def signal_button_clicked_sender_stop(self, button):
		if not self.sender_thread:
			return
		if not gui_utilities.show_dialog_yes_no('King Phisher Is Sending Messages', self.parent, 'Are you sure you want to stop?'):
			return
		self.sender_thread.stop()
		self.gobjects['button_mail_sender_stop'].set_sensitive(False)
		self.gobjects['button_mail_sender_start'].set_sensitive(True)
		self.gobjects['togglebutton_mail_sender_pause'].set_property('active', False)
		self.gobjects['togglebutton_mail_sender_pause'].set_sensitive(False)

	def signal_button_toggled_sender_pause(self, button):
		if not self.sender_thread:
			return
		if button.get_property('active'):
			self.sender_thread.pause()
		else:
			self.sender_thread.unpause()

	def signal_kpc_exit(self, kpc):
		if self.sender_thread and self.sender_thread.is_alive():
			self.logger.info('stopping the sender thread because the client is exiting')
			self.sender_thread.stop()

	def signal_kpc_exit_confirm(self, kpc):
		if not self.sender_thread:
			return
		if not self.sender_thread.is_alive():
			return
		if gui_utilities.show_dialog_yes_no('King Phisher Is Sending Messages', self.parent, 'Are you sure you want to exit?'):
			return
		kpc.emit_stop_by_name('exit-confirm')

	def signal_textview_populate_popup(self, textview, menu):
		menu_item = Gtk.MenuItem.new_with_label('Clear All')
		menu_item.connect('activate', self.signal_activate_popup_menu_clear_all)
		menu_item.show()
		menu.append(menu_item)
		return True

	def signal_textview_size_allocate_autoscroll(self, textview, allocation):
		scrolled_window = self.gobjects['scrolledwindow_mail_sender_progress']
		adjustment = scrolled_window.get_vadjustment()
		adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())

	def text_insert(self, message):
		"""
		Insert text into the :py:attr:`~.MailSenderSendTab.textbuffer`.

		:param str message: The text to insert.
		"""
		self.textbuffer.insert(self.textbuffer_iter, message)

	def notify_status(self, message):
		"""
		A call back use by :py:class:`.MailSenderThread` to update
		general status information.

		:param str message: The status message.
		"""
		self.text_insert(message)

	def notify_sent(self, emails_done, emails_total):
		"""
		A call back use by :py:class:`.MailSenderThread` to notify when
		an email has been successfully sent to the SMTP server.

		:param int emails_done: The number of email messages that have been sent.
		:param int emails_total: The total number of email messages that need to be sent.
		"""
		self.progressbar.set_fraction(float(emails_done) / float(emails_total))

	def sender_start_failure(self, message=None, text=None, retry=False):
		"""
		Handle a failure in starting the message sender thread and
		perform any necessary clean up.

		:param message: A message to shown in an error popup dialog.
		:type message: str, tuple
		:param text message: A message to be inserted into the text buffer.
		:param bool retry: The operation will be attempted again.
		"""
		if text:
			self.text_insert(text)
		self.gobjects['button_mail_sender_stop'].set_sensitive(False)
		self.gobjects['button_mail_sender_start'].set_sensitive(True)
		if isinstance(message, str):
			gui_utilities.show_dialog_error(message, self.parent)
		elif isinstance(message, tuple) and len(message) == 2:
			gui_utilities.show_dialog_error(message[0], self.parent, message[1])
		if not retry:
			self.sender_thread = None

	def notify_stopped(self):
		"""
		A call back use by :py:class:`.MailSenderThread` to notify when
		the thread has stopped.
		"""
		self.progressbar.set_fraction(1)
		self.gobjects['button_mail_sender_stop'].set_sensitive(False)
		self.gobjects['togglebutton_mail_sender_pause'].set_property('active', False)
		self.gobjects['togglebutton_mail_sender_pause'].set_sensitive(False)
		self.gobjects['button_mail_sender_start'].set_sensitive(True)
		self.sender_thread = None

class MailSenderPreviewTab(object):
	"""
	This tab uses the WebKit engine to render the HTML of an email so it can be
	previewed before it is sent.
	"""
	def __init__(self, config, parent):
		"""
		:param dict config: The King Phisher client configuration.
		:param parent: The parent window for this object.
		:type parent: :py:class:`Gtk.Window`
		"""
		self.label = Gtk.Label(label='Preview')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		self.config = config
		self.parent = parent

		self.box = Gtk.Box()
		self.box.set_property('orientation', Gtk.Orientation.VERTICAL)
		self.box.show()
		self.webview = WebKitX.WebView()
		"""The :py:class:`WebKit2.WebView` object used to render the message HTML."""
		if has_webkit2:
			self.webview.get_context().set_cache_model(WebKitX.CacheModel.DOCUMENT_VIEWER)
		self.webview.show()
		scrolled_window = Gtk.ScrolledWindow()
		scrolled_window.add(self.webview)
		scrolled_window.show()
		self.box.pack_start(scrolled_window, True, True, 0)
		self.file_monitor = None

	def _html_file_changed(self, path, monitor_event):
		if monitor_event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
			self.load_html_file()

	def load_html_file(self):
		html_file = self.config.get('mailer.html_file')
		if not (html_file and os.path.isfile(html_file) and os.access(html_file, os.R_OK)):
			return
		with open(html_file, 'rb') as file_h:
			html_data = file_h.read()
		html_data = str(html_data.decode('utf-8', 'ignore'))
		html_data = mailer.format_message(html_data, self.config)
		html_file_uri = urllib.parse.urlparse(html_file, 'file').geturl()
		if not html_file_uri.startswith('file://'):
			html_file_uri = 'file://' + html_file_uri
		if has_webkit2:
			self.webview.load_html(html_data, html_file_uri)
		else:
			self.webview.load_html_string(html_data, html_file_uri)

	def show_tab(self):
		"""Configure the webview to preview the the message HTML file."""
		if self.file_monitor and self.file_monitor.path == self.config['mailer.html_file']:
			return
		if not self.config['mailer.html_file']:
			if self.file_monitor:
				self.file_monitor.stop()
				self.file_monitor = None
			return
		self.load_html_file()
		self.file_monitor = gui_utilities.FileMonitor(self.config['mailer.html_file'], self._html_file_changed)

class MailSenderEditTab(gui_utilities.GladeGObject):
	"""
	This is the tab which adds basic text edition for changing an email
	template.
	"""
	gobject_ids = [
		'toolbutton_save_as_html_file',
		'toolbutton_save_html_file',
		'view_html_file'
	]
	top_gobject = 'box'
	def __init__(self, *args, **kwargs):
		self.label = Gtk.Label(label='Edit')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderEditTab, self).__init__(*args, **kwargs)
		self.textview = self.gobjects['view_html_file']
		"""The :py:class:`Gtk.TextView` object of the editor."""
		self.textbuffer = GtkSource.Buffer()
		"""The :py:class:`Gtk.TextBuffer` used by the :py:attr:textview` attribute."""
		self.textview.set_buffer(self.textbuffer)
		self.textview.modify_font(Pango.FontDescription(self.config['text_font']))
		self.language_manager = GtkSource.LanguageManager()
		self.textbuffer.set_language(self.language_manager.get_language('html'))
		self.textbuffer.set_highlight_syntax(True)
		self.toolbutton_save_html_file = self.gobjects['toolbutton_save_html_file']
		self.textview.connect('populate-popup', self.signal_textview_populate_popup)

		scheme_manager = GtkSource.StyleSchemeManager()
		style_scheme_name = self.config['text_source_theme']
		style_scheme = scheme_manager.get_scheme(style_scheme_name)
		if style_scheme:
			self.textbuffer.set_style_scheme(style_scheme)
		else:
			self.logger.error("invalid GTK source theme: '{0}'".format(style_scheme_name))
		self.file_monitor = None

	def _html_file_changed(self, path, monitor_event):
		if monitor_event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
			self.load_html_file()

	def load_html_file(self):
		html_file = self.config.get('mailer.html_file')
		if not (html_file and os.path.isfile(html_file) and os.access(html_file, os.R_OK)):
			self.toolbutton_save_html_file.set_sensitive(False)
			self.textview.set_property('editable', False)
			return
		self.toolbutton_save_html_file.set_sensitive(True)
		self.textview.set_property('editable', True)
		with open(html_file, 'rb') as file_h:
			html_data = file_h.read()
		html_data = str(html_data.decode('utf-8', 'ignore'))
		self.textbuffer.begin_not_undoable_action()
		self.textbuffer.set_text(html_data)
		self.textbuffer.end_not_undoable_action()

	def signal_toolbutton_open(self, button):
		dialog = gui_utilities.FileChooser('Choose File', self.parent)
		dialog.quick_add_filter('HTML Files', ['*.htm', '*.html'])
		dialog.quick_add_filter('All Files', '*')
		response = dialog.run_quick_open()
		dialog.destroy()
		if not response:
			return False
		self.config['mailer.html_file'] = response['target_path']
		self.show_tab()
		return True

	def signal_toolbutton_save(self, toolbutton):
		html_file = self.config.get('mailer.html_file')
		if not html_file:
			return
		if not gui_utilities.show_dialog_yes_no('Save HTML the file?', self.parent):
			return
		text = self.textbuffer.get_text(self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter(), False)
		html_file_h = open(html_file, 'w')
		html_file_h.write(text)
		html_file_h.close()

	def signal_toolbutton_save_as(self, toolbutton):
		dialog = gui_utilities.FileChooser('Save HTML File', self.parent)
		html_file = self.config.get('mailer.html_file')
		if html_file:
			current_name = os.path.basename(html_file)
		else:
			current_name = 'message.html'
		response = dialog.run_quick_save(current_name=current_name)
		dialog.destroy()
		if not response:
			return
		destination_file = response['target_path']
		text = self.textbuffer.get_text(self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter(), False)
		html_file_h = open(destination_file, 'w')
		html_file_h.write(text)
		html_file_h.close()
		self.config['mailer.html_file'] = destination_file
		self.toolbutton_save_html_file.set_sensitive(True)

	def signal_toolbutton_template_wiki(self, toolbutton):
		utilities.open_uri('https://github.com/securestate/king-phisher/wiki/Templates#message-templates')

	def signal_textview_populate_popup(self, textview, menu):
		# create and populate the 'Insert' submenu
		insert_submenu = Gtk.Menu.new()
		menu_item = Gtk.MenuItem.new_with_label('Insert')
		menu_item.set_submenu(insert_submenu)
		menu.append(menu_item)
		menu_item.show()

		menu_item = Gtk.MenuItem.new_with_label('Inline Image')
		menu_item.connect('activate', self.signal_activate_popup_menu_insert_image)
		insert_submenu.append(menu_item)

		menu_item = Gtk.MenuItem.new_with_label('Tracking Image Tag')
		menu_item.connect('activate', self.signal_activate_popup_menu_insert, '{{ tracking_dot_image_tag }}')
		insert_submenu.append(menu_item)

		menu_item = Gtk.MenuItem.new_with_label('Webserver URL')
		menu_item.connect('activate', self.signal_activate_popup_menu_insert, '{{ url.webserver }}')
		insert_submenu.append(menu_item)

		# create and populate the 'Date & Time' submenu
		insert_datetime_submenu = Gtk.Menu.new()
		menu_item = Gtk.MenuItem.new_with_label('Date & Time')
		menu_item.set_submenu(insert_datetime_submenu)
		insert_submenu.append(menu_item)
		menu_item.show()

		formats = [
			'%a %B %d, %Y',
			'%b %d, %y',
			'%m/%d/%y',
			None,
			'%I:%M %p',
			'%H:%M:%S'
		]
		dt_now = datetime.datetime.now()
		for fmt in formats:
			if fmt:
				menu_item = Gtk.MenuItem.new_with_label(dt_now.strftime(fmt))
				menu_item.connect('activate', self.signal_activate_popup_menu_insert, "{{{{ time.local | strftime('{0}') }}}}".format(fmt))
			else:
				menu_item = Gtk.SeparatorMenuItem()
			insert_datetime_submenu.append(menu_item)

		insert_submenu.show_all()
		return True

	def signal_activate_popup_menu_insert(self, widget, text):
		self.textbuffer.insert_at_cursor(text)
		return True

	def signal_activate_popup_menu_insert_image(self, widget):
		dialog = gui_utilities.FileChooser('Choose Image', self.parent)
		dialog.quick_add_filter('Images', ['*.gif', '*.jpeg', '*.jpg', '*.png'])
		dialog.quick_add_filter('All Files', '*')
		response = dialog.run_quick_open()
		dialog.destroy()
		if not response:
			return
		target_path = response['target_path']
		target_path = utilities.escape_single_quote(target_path)
		text = "{{{{ inline_image('{0}') }}}}".format(target_path)
		return self.signal_activate_popup_menu_insert(widget, text)

	def show_tab(self):
		"""Load the message HTML file from disk and configure the tab for editing."""
		if self.file_monitor and self.file_monitor.path == self.config['mailer.html_file']:
			return
		if not self.config['mailer.html_file']:
			if self.file_monitor:
				self.file_monitor.stop()
				self.file_monitor = None
			return
		self.load_html_file()
		self.file_monitor = gui_utilities.FileMonitor(self.config['mailer.html_file'], self._html_file_changed)

class MailSenderConfigurationTab(gui_utilities.GladeGObject):
	"""
	This is the tab which allows the user to configure and set parameters
	for sending messages as part of a campaign.
	"""
	gobject_ids = [
		'entry_webserver_url',
		'entry_company_name',
		'entry_source_email',
		'entry_source_email_smtp',
		'entry_source_email_alias',
		'entry_subject',
		'entry_reply_to_email',
		'entry_html_file',
		'entry_target_file',
		'entry_attachment_file',
		'combobox_importance',
		'combobox_sensitivity'
	]
	config_prefix = 'mailer.'
	top_gobject = 'box'
	top_level_dependencies = [
		'MsgImportance',
		'MsgSensitivity'
	]
	def __init__(self, *args, **kwargs):
		self.label = Gtk.Label(label='Configuration')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderConfigurationTab, self).__init__(*args, **kwargs)
		self.parent.connect('exit', self.signal_kpc_exit)

	def signal_button_clicked_verify(self, button):
		target_url = self.gobjects['entry_webserver_url'].get_text()
		try:
			test_webserver_url(target_url, self.config['server_config']['server.secret_id'])
		except Exception as error:
			error_description = None
			if isinstance(error, urllib.request.URLError) and hasattr(error, 'reason') and isinstance(error.reason, Exception):
				error = error.reason
			if isinstance(error, urllib.request.HTTPError) and error.getcode():
				self.logger.warning("verify url HTTPError: {0} {1}".format(error.getcode(), error.reason))
				error_description = "HTTP status {0} {1}".format(error.getcode(), error.reason)
			elif isinstance(error, socket.gaierror):
				self.logger.warning('verify url attempt failed, socket.gaierror')
				error_description = error.args[-1]
			elif isinstance(error, socket.timeout):
				self.logger.warning('verify url attempt failed, connection timeout occurred')
				error_description = 'Connection timed out'
			else:
				self.logger.warning('unknown verify url exception: ' + repr(error))
			gui_utilities.show_dialog_warning('Unable To Open The Web Server URL', self.parent, error_description)
			return
		gui_utilities.show_dialog_info('Successfully Opened The Web Server URL', self.parent)
		return

	def signal_entry_activate_open_file(self, entry):
		dialog = gui_utilities.FileChooser('Choose File', self.parent)
		if entry == self.gobjects.get('entry_html_file'):
			dialog.quick_add_filter('HTML Files', ['*.htm', '*.html'])
		elif entry == self.gobjects.get('entry_target_file'):
			dialog.quick_add_filter('CSV Files', '*.csv')
		dialog.quick_add_filter('All Files', '*')
		response = dialog.run_quick_open()
		dialog.destroy()
		if not response:
			return False
		entry.set_text(response['target_path'])
		return True

	def signal_entry_backspace(self, entry):
		entry.set_text('')
		return True

	def signal_kpc_exit(self, kpc):
		self.objects_save_to_config()

class MailSenderTab(object):
	"""
	The King Phisher client top-level 'Send Messages' tab. This object
	manages the sub-tabs which display useful information for
	configuring, previewing and sending messages as part of a campaign.
	"""
	def __init__(self, config, parent, application):
		"""
		:param dict config: The King Phisher client configuration.
		:param parent: The parent window for this object.
		:type parent: :py:class:`Gtk.Window`
		:param application: The main client application instance.
		:type application: :py:class:`Gtk.Application`
		"""
		self.config = config
		self.parent = parent
		self.application = application
		self.box = Gtk.Box()
		self.box.set_property('orientation', Gtk.Orientation.VERTICAL)
		self.box.show()
		self.label = Gtk.Label(label='Send Messages')
		"""The :py:class:`Gtk.Label` representing this tabs name."""

		self.notebook = Gtk.Notebook()
		""" The :py:class:`Gtk.Notebook` for holding sub-tabs."""
		self.notebook.connect('switch-page', self.signal_notebook_switch_page)
		self.notebook.set_scrollable(True)
		self.box.pack_start(self.notebook, True, True, 0)

		self.tabs = {}
		"""A dict object holding the sub tabs managed by this object."""
		current_page = self.notebook.get_current_page()
		self.last_page_id = current_page

		config_tab = MailSenderConfigurationTab(self.config, self.parent)
		self.tabs['config'] = config_tab
		self.notebook.append_page(config_tab.box, config_tab.label)

		edit_tab = MailSenderEditTab(self.config, self.parent)
		self.tabs['edit'] = edit_tab
		self.notebook.append_page(edit_tab.box, edit_tab.label)

		preview_tab = MailSenderPreviewTab(self.config, self.parent)
		self.tabs['preview'] = preview_tab
		self.notebook.append_page(preview_tab.box, preview_tab.label)

		send_messages_tab = MailSenderSendTab(self.config, self.parent)
		self.tabs['send_messages'] = send_messages_tab
		self.notebook.append_page(send_messages_tab.box, send_messages_tab.label)

		for tab in self.tabs.values():
			tab.box.show()
		self.notebook.show()

	def signal_notebook_switch_page(self, notebook, current_page, index):
		previous_page = notebook.get_nth_page(self.last_page_id)
		self.last_page_id = index
		config_tab = self.tabs.get('config')
		edit_tab = self.tabs.get('edit')
		preview_tab = self.tabs.get('preview')

		if config_tab and previous_page == config_tab.box:
			config_tab.objects_save_to_config()
		elif edit_tab and previous_page == edit_tab.box:
			for _ in range(1):
				html_file = self.config.get('mailer.html_file')
				if not html_file:
					break
				text = edit_tab.textbuffer.get_text(edit_tab.textbuffer.get_start_iter(), edit_tab.textbuffer.get_end_iter(), False)
				if not text:
					break
				old_text = open(html_file, 'r').read()
				if old_text == text:
					break
				if not gui_utilities.show_dialog_yes_no('Save HTML the file?', self.parent):
					break
				html_file_h = open(html_file, 'w')
				html_file_h.write(text)
				html_file_h.close()

		if config_tab and current_page == config_tab.box:
			config_tab.objects_load_from_config()
		elif edit_tab and current_page == edit_tab.box:
			edit_tab.show_tab()
		elif preview_tab and current_page == preview_tab.box:
			preview_tab.show_tab()

	def export_message_data(self):
		"""
		Gather and prepare the components of the mailer tab to be exported into
		a message archive file suitable for restoring at a later point in time.
		"""
		config_tab = self.tabs.get('config')
		if not config_tab:
			self.logger.warning('attempted to export message data while the config tab was unavailable')
			return
		config_prefix = config_tab.config_prefix
		config_tab.objects_save_to_config()
		dialog = gui_utilities.FileChooser('Export Message Configuration', self.parent)
		response = dialog.run_quick_save('message.kpm')
		dialog.destroy()
		if not response:
			return
		message_config = {}
		config_keys = (key for key in self.config.keys() if key.startswith(config_prefix))
		for config_key in config_keys:
			message_config[config_key[7:]] = self.config[config_key]
		export.message_data_to_kpm(message_config, response['target_path'])

	def import_message_data(self):
		"""
		Process a previously exported message archive file and restore the
		message data, settings, and applicable files from it.
		"""
		config_tab = self.tabs.get('config')
		if not config_tab:
			self.logger.warning('attempted to import message data while the config tab was unavailable')
			return
		config_prefix = config_tab.config_prefix
		config_tab.objects_save_to_config()
		dialog = gui_utilities.FileChooser('Import Message Configuration', self.parent)
		dialog.quick_add_filter('King Phisher Message Files', '*.kpm')
		dialog.quick_add_filter('All Files', '*')
		response = dialog.run_quick_open()
		dialog.destroy()
		if not response:
			return
		target_file = response['target_path']

		dialog = gui_utilities.FileChooser('Destination Directory', self.parent)
		response = dialog.run_quick_select_directory()
		dialog.destroy()
		if not response:
			return
		dest_dir = response['target_path']
		try:
			message_data = export.message_data_from_kpm(target_file, dest_dir)
		except KingPhisherInputValidationError as error:
			gui_utilities.show_dialog_error('Import Error', self.parent, error.message.capitalize() + '.')
			return

		config_keys = set(key for key in self.config.keys() if key.startswith(config_prefix))
		config_types = dict(zip(config_keys, map(type, config_keys)))
		for key, value in message_data.items():
			key = config_prefix + key
			if not key in config_keys:
				continue
			self.config[key] = value
			config_keys.remove(key)
		for unset_key in config_keys:
			config_type = config_types[unset_key]
			if not config_type in (bool, dict, int, list, str, tuple):
				continue
			self.config[unset_key] = config_type()
		config_tab.objects_load_from_config()
		gui_utilities.show_dialog_info('Successfully imported the message', self.parent)
