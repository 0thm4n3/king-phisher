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

import collections
import os
import urllib
import urllib2
import urlparse

from king_phisher.client import gui_utilities
from king_phisher.client.login import KingPhisherClientSSHLoginDialog
from king_phisher.client.mailer import format_message, MailSenderThread

from gi.repository import Gtk
from gi.repository import WebKit

class MailSenderSendMessagesTab(gui_utilities.UtilityGladeGObject):
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
		self.label = Gtk.Label('Send Messages')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderSendMessagesTab, self).__init__(*args, **kwargs)
		self.textview = self.gobjects['textview_mail_sender_progress']
		"""The :py:class:`Gtk.TextView` object that renders text status messages."""
		self.textbuffer = self.textview.get_buffer()
		"""The :py:class:`Gtk.TextBuffer` instance associated with :py:attr:`~.MailSenderSendMessagesTab.textview`."""
		self.textbuffer_iter = self.textbuffer.get_start_iter()
		self.progressbar = self.gobjects['progressbar_mail_sender']
		"""The :py:class:`Gtk.ProgressBar` instance which is used to display progress of sending messages."""
		self.pause_button = self.gobjects['togglebutton_mail_sender_pause']
		self.sender_thread = None
		"""The :py:class:`.MailSenderThread` instance that is being used to send messages."""

	def signal_button_clicked_sender_start(self, button):
		required_settings = {
			'mailer.webserver_url': 'Web Server URL',
			'mailer.company_name': 'Company Name',
			'mailer.source_email': 'Source Email',
			'mailer.subject': 'Friendly Alias',
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
				gui_utilities.show_dialog_warning('Invalid Option Configuration', self.parent, "Setting: '{0}'\nReason: File could not be read".format(setting_name))
				return
		if not self.config.get('smtp_server'):
			gui_utilities.show_dialog_warning('Missing SMTP Server Setting', self.parent, 'Please configure the SMTP server')
			return
		if self.sender_thread:
			return
		self.parent.save_config()
		self.gobjects['button_mail_sender_start'].set_sensitive(False)
		self.gobjects['button_mail_sender_stop'].set_sensitive(True)
		self.progressbar.set_fraction(0)
		self.sender_thread = MailSenderThread(self.config, self.config['mailer.target_file'], self, self.parent.rpc)

		# Connect to the SMTP server
		if self.config['smtp_ssh_enable']:
			while True:
				self.text_insert('Connecting To SSH... ')
				login_dialog = KingPhisherClientSSHLoginDialog(self.config, self.parent)
				login_dialog.objects_load_from_config()
				response = login_dialog.interact()
				if response == Gtk.ResponseType.CANCEL:
					self.sender_start_failure(text='Canceled.\n')
					return
				if self.sender_thread.server_ssh_connect():
					self.text_insert('Done.\n')
					break
				self.sender_start_failure('Failed to connect to SSH', 'Failed.\n')
		self.text_insert('Connecting To SMTP Server... ')
		if not self.sender_thread.server_smtp_connect():
			self.sender_start_failure('Failed to connect to SMTP', 'Failed.\n')
			return
		self.text_insert('Done.\n')

		parsed_target_url = urlparse.urlparse(self.config['mailer.webserver_url'])
		landing_page_hostname = parsed_target_url.netloc
		landing_page = parsed_target_url.path
		landing_page = landing_page.lstrip('/')
		self.parent.rpc('campaign/landing_page/new', self.config['campaign_id'], landing_page_hostname, landing_page)

		self.sender_thread.start()
		self.gobjects['togglebutton_mail_sender_pause'].set_sensitive(True)

	def signal_button_clicked_sender_stop(self, button):
		if not self.sender_thread:
			return
		if not gui_utilities.show_dialog_yes_no('Are you sure you want to stop?', self.parent):
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

	def signal_textview_size_allocate_autoscroll(self, textview, allocation):
		scrolled_window = self.gobjects['scrolledwindow_mail_sender_progress']
		adjustment = scrolled_window.get_vadjustment()
		adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())

	def text_insert(self, message):
		"""
		Insert text into the :py:attr:`~.MailSenderSendMessagesTab.textbuffer`.

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

	def sender_start_failure(self, message=None, text=None):
		"""
		Handle a failure in starting the message sender thread and
		perform any necessary clean up.

		:param str message: A message to shown in an error popup dialog.
		:param text message: A message to be inserted into the text buffer.
		"""
		if text:
			self.text_insert(text)
		self.gobjects['button_mail_sender_stop'].set_sensitive(False)
		self.gobjects['button_mail_sender_start'].set_sensitive(True)
		if message:
			gui_utilities.show_dialog_error(message, self.parent)
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
	This tab uses webkit to render the HTML of an email so it can be
	previewed before it is sent.
	"""
	def __init__(self, config, parent):
		"""
		:param dict config: The King Phisher client configuration.
		:param parent: The parent window for this object.
		:type parent: :py:class:`Gtk.Window`
		"""
		self.label = Gtk.Label('Preview')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		self.config = config
		self.parent = parent

		self.box = Gtk.Box()
		self.box.set_property('orientation', Gtk.Orientation.VERTICAL)
		self.box.show()
		self.webview = WebKit.WebView()
		"""The :py:class:`WebKit.WebView` object used to render the message HTML."""
		self.webview.show()
		scrolled_window = Gtk.ScrolledWindow()
		scrolled_window.add(self.webview)
		scrolled_window.show()
		self.box.pack_start(scrolled_window, True, True, 0)

class MailSenderEditTab(gui_utilities.UtilityGladeGObject):
	"""
	This is the tab which adds basic text edition for changing an email
	template.
	"""
	gobject_ids = [
		'button_save_as_html_file',
		'button_save_html_file',
		'textview_html_file'
	]
	top_gobject = 'box'
	def __init__(self, *args, **kwargs):
		self.label = Gtk.Label('Edit')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderEditTab, self).__init__(*args, **kwargs)
		self.textview = self.gobjects['textview_html_file']
		"""The :py:class:`Gtk.TextView` object of the editor."""
		self.textbuffer = self.textview.get_buffer()
		"""The :py:class:`Gtk.TextBuffer` used by the :py:attr:textview` attribute."""
		self.button_save_html_file = self.gobjects['button_save_html_file']

	def signal_button_save_as(self, button):
		html_file = self.config.get('mailer.html_file')
		if not html_file:
			return
		dialog = gui_utilities.UtilityFileChooser('Save HTML File', self.parent)
		response = dialog.run_quick_save(current_name=os.path.basename(html_file))
		dialog.destroy()
		if not response:
			return
		destination_file = response['target_filename']
		text = self.textbuffer.get_text(self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter(), False)
		html_file_h = open(destination_file, 'w')
		html_file_h.write(text)
		html_file_h.close()
		self.config['mailer.html_file'] = destination_file

	def signal_button_save(self, button):
		html_file = self.config.get('mailer.html_file')
		if not html_file:
			return
		if not gui_utilities.show_dialog_yes_no("Save HTML File?", self.parent):
			return
		text = self.textbuffer.get_text(self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter(), False)
		html_file_h = open(html_file, 'w')
		html_file_h.write(text)
		html_file_h.close()

class MailSenderConfigTab(gui_utilities.UtilityGladeGObject):
	"""
	This is the tab which allows the user to configure and set parameters
	for sending messages as part of a campaign.
	"""
	gobject_ids = [
		'entry_webserver_url',
		'entry_company_name',
		'entry_source_email',
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
		self.label = Gtk.Label('Config')
		"""The :py:class:`Gtk.Label` representing this tabs name."""
		super(MailSenderConfigTab, self).__init__(*args, **kwargs)

	def signal_button_clicked_verify(self, button):
		target_url = self.gobjects['entry_webserver_url'].get_text()
		try:
			parsed_url = urlparse.urlparse(target_url)
			query = urlparse.parse_qs(parsed_url.query)
			query['id'] = [self.config['server_config']['server.secret_id']]
			query = urllib.urlencode(query, True)
			target_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, query, parsed_url.fragment))
			urllib2.urlopen(target_url, timeout=5)
		except:
			gui_utilities.show_dialog_warning('Unable To Open The Web Server URL', self.parent)
			return
		gui_utilities.show_dialog_info('Successfully Opened The Web Server URL', self.parent)
		return

	def signal_entry_activate_open_file(self, entry):
		dialog = gui_utilities.UtilityFileChooser('Choose File')
		if entry == self.gobjects.get('entry_html_file'):
			dialog.quick_add_filter('HTML Files', ['*.htm', '*.html'])
		elif entry == self.gobjects.get('entry_target_file'):
			dialog.quick_add_filter('CSV Files', '*.csv')
		dialog.quick_add_filter('All Files', '*')
		response = dialog.run_quick_open()
		dialog.destroy()
		if not response:
			return False
		entry.set_text(response['target_filename'])
		return True

	def signal_entry_backspace(self, entry):
		entry.set_text('')
		return True

class MailSenderTab(object):
	"""
	The King Phisher client top-level 'Send Messages' tab. This object
	manages the sub-tabs which display useful information for
	configuring, previewing and sending messages as part of a campaign.
	"""
	def __init__(self, config, parent):
		"""
		:param dict config: The King Phisher client configuration.
		:param parent: The parent window for this object.
		:type parent: :py:class:`Gtk.Window`
		"""
		self.config = config
		self.parent = parent
		self.box = Gtk.Box()
		self.box.set_property('orientation', Gtk.Orientation.VERTICAL)
		self.box.show()
		self.label = Gtk.Label('Send Messages')
		"""The :py:class:`Gtk.Label` representing this tabs name."""

		self.notebook = Gtk.Notebook()
		""" The :py:class:`Gtk.Notebook` for holding sub-tabs."""
		self.notebook.connect('switch-page', self._tab_changed)
		self.notebook.set_scrollable(True)
		self.box.pack_start(self.notebook, True, True, 0)

		self.tabs = {}
		"""A dict object holding the sub tabs managed by this object."""
		current_page = self.notebook.get_current_page()
		self.last_page_id = current_page

		config_tab = MailSenderConfigTab(self.config, self.parent)
		self.tabs['config'] = config_tab
		self.notebook.append_page(config_tab.box, config_tab.label)

		edit_tab = MailSenderEditTab(self.config, self.parent)
		self.tabs['edit'] = edit_tab
		self.notebook.append_page(edit_tab.box, edit_tab.label)

		preview_tab = MailSenderPreviewTab(self.config, self.parent)
		self.tabs['preview'] = preview_tab
		self.notebook.append_page(preview_tab.box, preview_tab.label)

		send_messages_tab = MailSenderSendMessagesTab(self.config, self.parent)
		self.tabs['send_messages'] = send_messages_tab
		self.notebook.append_page(send_messages_tab.box, send_messages_tab.label)

		for tab in self.tabs.values():
			tab.box.show()
		self.notebook.show()

	def _tab_changed(self, notebook, current_page, index):
		previous_page = notebook.get_nth_page(self.last_page_id)
		self.last_page_id = index
		config_tab = self.tabs.get('config')
		edit_tab = self.tabs.get('edit')
		preview_tab = self.tabs.get('preview')
		progress_tab = self.tabs.get('progress')

		if config_tab and previous_page == config_tab.box:
			config_tab.objects_save_to_config()
		elif edit_tab and previous_page == edit_tab.box:
			for i in xrange(1):
				html_file = self.config.get('mailer.html_file')
				if not html_file:
					break
				text = edit_tab.textbuffer.get_text(edit_tab.textbuffer.get_start_iter(), edit_tab.textbuffer.get_end_iter(), False)
				if not text:
					break
				old_text = open(html_file, 'r').read()
				if old_text == text:
					break
				if not gui_utilities.show_dialog_yes_no("Save HTML File?", self.parent):
					break
				html_file_h = open(html_file, 'w')
				html_file_h.write(text)
				html_file_h.close()

		if config_tab and current_page == config_tab.box:
			config_tab.objects_load_from_config()
		if edit_tab and current_page == edit_tab.box:
			html_file = self.config.get('mailer.html_file')
			if not (html_file and os.path.isfile(html_file) and os.access(html_file, os.R_OK)):
				edit_tab.button_save_html_file.set_sensitive(False)
				edit_tab.textview.set_property('editable', False)
				return
			edit_tab.button_save_html_file.set_sensitive(True)
			edit_tab.textview.set_property('editable', True)
			edit_tab.textbuffer.set_text(open(html_file, 'r').read())
		elif preview_tab and current_page == preview_tab.box:
			html_file = self.config.get('mailer.html_file')
			if not (html_file and os.path.isfile(html_file) and os.access(html_file, os.R_OK)):
				return
			html_file_uri = urlparse.urlparse(html_file, 'file').geturl()
			html_data = open(html_file, 'r').read()
			html_data = format_message(html_data, self.config)
			preview_tab.webview.load_html_string(html_data, html_file_uri)
