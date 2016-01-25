#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/assistants/campaign_creation.py
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

from king_phisher import utilities
from king_phisher.client import gui_utilities
from king_phisher.constants import ColorHexCode
from king_phisher.third_party import AdvancedHTTPServer

from gi.repository import Gtk
from gi.repository import Pango

__all__ = ('CampaignAssistant',)

class CampaignAssistant(gui_utilities.GladeGObject):
	"""
	Display an assistant which walks the user through creating a new campaign or
	configuring an existing campaign. If no *campaign_id* is specified a new
	campaign will be created.
	"""
	dependencies = gui_utilities.GladeDependencies(
		children=(
			'calendar_campaign_expiration',
			'checkbutton_alert_subscribe',
			'checkbutton_expire_campaign',
			'checkbutton_reject_after_credentials',
			'combobox_campaign_type',
			'combobox_company_existing',
			'combobox_company_industry',
			'entry_campaign_name',
			'entry_campaign_description',
			'entry_company_new_name',
			'entry_company_new_description',
			'entry_company_url_main',
			'entry_company_url_email',
			'entry_company_url_remote_access',
			'frame_campaign_expiration',
			'frame_company_existing',
			'frame_company_new',
			'image_intro_title',
			'label_confirm_body',
			'label_confirm_title',
			'label_intro_body',
			'label_intro_title',
			'radiobutton_company_existing',
			'radiobutton_company_new',
			'radiobutton_company_none',
			'spinbutton_campaign_expiration_hour',
			'spinbutton_campaign_expiration_minute'
		),
		top_level=(
			'ClockHourAdjustment',
			'ClockMinuteAdjustment'
		)
	)
	top_gobject = 'assistant'
	objects_persist = False
	def __init__(self, application, campaign_id=None):
		"""
		:param application: The application instance which this object belongs to.
		:type application: :py:class:`~king_phisher.client.application.KingPhisherClientApplication`
		:param campaign_id: The ID of the campaign to edit.
		"""
		super(CampaignAssistant, self).__init__(application)
		self.campaign_id = campaign_id
		self._close_ready = True
		self._page_titles = {}
		for page_n in range(self.assistant.get_n_pages()):
			page = self.assistant.get_nth_page(page_n)
			page_title = self.assistant.get_page_title(page)
			if page_title:
				self._page_titles[page_title] = page_n

		self._set_comboboxes()
		self._set_defaults()

		if not self.config['server_config']['server.require_id']:
			self.gobjects['checkbutton_reject_after_credentials'].set_sensitive(False)
			self.gobjects['checkbutton_reject_after_credentials'].set_property('active', False)

		confirm_preamble = 'Verify all settings are correct in the previous sections'
		if campaign_id:
			# re-configuring an existing campaign
			self.gobjects['label_confirm_body'].set_text(confirm_preamble + ', then hit "Apply" to update the King Phisher campaign with the new settings.')
			self.gobjects['label_intro_body'].set_text('This assistant will walk you through reconfiguring the selected King Phisher campaign.')
			self.gobjects['label_intro_title'].set_text('Configure Campaign')
		else:
			# creating a new campaign
			self.gobjects['label_confirm_body'].set_text(confirm_preamble + ', then hit "Apply" to create the new King Phisher campaign.')
			self.gobjects['label_intro_body'].set_text('This assistant will walk you through creating and configuring a new King Phisher campaign.')
			self.gobjects['label_intro_title'].set_text('New Campaign')

	@property
	def campaign_name(self):
		"""
		The string value of the configured campaign name. This may be set even
		when the campaign was not created, which would be the case if the user
		closed the window.
		"""
		return self.gobjects['entry_campaign_name'].get_text()

	@property
	def is_editing_campaign(self):
		return self.campaign_id is not None

	@property
	def is_new_campaign(self):
		return self.campaign_id is None

	def _set_comboboxes(self):
		"""Set up all the comboboxes and load the data for their models."""
		description_font_desc = Pango.FontDescription()
		description_font_desc.set_style(Pango.Style.ITALIC)

		for combobox in ('campaign_type', 'company_existing', 'company_industry'):
			combobox = self.gobjects['combobox_' + combobox]
			model = Gtk.ListStore(int, str, str)
			model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
			combobox.set_model(model)
			renderer = Gtk.CellRendererText()
			renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
			renderer.set_property('font-desc', description_font_desc)
			renderer.set_property('foreground', ColorHexCode.GRAY)
			renderer.set_property('max-width-chars', 20)
			combobox.pack_start(renderer, True)
			combobox.add_attribute(renderer, 'text', 2)

		combobox = self.gobjects['combobox_campaign_type']
		model = combobox.get_model()
		model.clear()
		for row in self.application.rpc.remote_table('campaign_types'):
			model.append((row.id, row.name, row.description))

		combobox = self.gobjects['combobox_company_existing']
		model = combobox.get_model()
		model.clear()
		for row in self.application.rpc.remote_table('companies'):
			model.append((row.id, row.name, row.description))

		combobox = self.gobjects['combobox_company_industry']
		model = combobox.get_model()
		model.clear()
		for row in self.application.rpc.remote_table('industries'):
			model.append((row.id, row.name, row.description))

	def _set_defaults(self):
		"""
		Set any default values for widgets. Also load settings from the existing
		campaign if one was specified.
		"""
		calendar = self.gobjects['calendar_campaign_expiration']
		default_day = datetime.datetime.today() + datetime.timedelta(days=31)
		gui_utilities.gtk_calendar_set_pydate(calendar, default_day)

		if self.campaign_id is None:
			return
		campaign = self.application.rpc.remote_table_row('campaigns', self.campaign_id, cache=True, refresh=True)

		self.gobjects['entry_campaign_name'].set_text(campaign.name)
		if campaign.description is not None:
			self.gobjects['entry_campaign_description'].set_text(campaign.description)
		if campaign.campaign_type_id is not None:
			combobox = self.gobjects['combobox_campaign_type']
			model = combobox.get_model()
			model_iter = gui_utilities.gtk_list_store_search(model, campaign.campaign_type_id, column=0)
			if model_iter is not None:
				combobox.set_active_iter(model_iter)

		self.gobjects['checkbutton_alert_subscribe'].set_property('active', self.application.rpc('campaign/alerts/is_subscribed', self.campaign_id))
		self.gobjects['checkbutton_reject_after_credentials'].set_property('active', campaign.reject_after_credentials)

		if campaign.company_id is not None:
			self.gobjects['radiobutton_company_existing'].set_active(True)
			combobox = self.gobjects['combobox_company_existing']
			model = combobox.get_model()
			model_iter = gui_utilities.gtk_list_store_search(model, campaign.company_id, column=0)
			if model_iter is not None:
				combobox.set_active_iter(model_iter)

		if campaign.expiration is not None:
			expiration = utilities.datetime_utc_to_local(campaign.expiration)
			self.gobjects['checkbutton_expire_campaign'].set_active(True)
			gui_utilities.gtk_calendar_set_pydate(self.gobjects['calendar_campaign_expiration'], expiration)
			self.gobjects['spinbutton_campaign_expiration_hour'].set_value(expiration.hour)
			self.gobjects['spinbutton_campaign_expiration_minute'].set_value(expiration.minute)

	def _get_entry(self, entry_name):
		"""
		Get the value of the specified entry then remove leading and trailing
		white space and finally determine if the string is empty, in which case
		return None.

		:param str entry_name: The name of the entry to retrieve text from.
		:return: Either the non-empty string or None.
		:rtype: None, str
		"""
		text = self.gobjects['entry_' + entry_name].get_text()
		text = text.strip()
		if not text:
			return None
		return text

	def _get_tag_from_combobox(self, combobox, db_table):
		model = combobox.get_model()
		model_iter = combobox.get_active_iter()
		if model_iter is None:
			campaign_type = combobox.get_child().get_text()
			if not campaign_type:
				return
			model_iter = gui_utilities.gtk_list_store_search(model, campaign_type, column=1)
			if model_iter is None:
				return self.application.rpc('db/table/insert', db_table, 'name', campaign_type)
		return model.get_value(model_iter, 0)

	def _get_company_existing_id(self):
		combobox_company = self.gobjects['combobox_company_existing']
		model = combobox_company.get_model()
		model_iter = combobox_company.get_active_iter()
		if model is None or model_iter is None:
			return
		return model.get_value(model_iter, 0)

	def _get_company_new_id(self):
		name = self.gobjects['entry_company_new_name'].get_text()
		name = name.strip()
		# check if this company name already exists in the model
		model = self.gobjects['combobox_company_existing'].get_model()
		model_iter = gui_utilities.gtk_list_store_search(model, name, column=1)
		if model_iter is not None:
			return model.get_value(model_iter, 0)
		# check if this company name already exists remotely
		remote_companies = list(self.application.rpc.remote_table('companies', query_filter={'name': name}))
		if len(remote_companies):
			return remote_companies[0].id

		company_id = self.application.rpc(
			'db/table/insert',
			'companies',
			('name', 'description', 'industry_id', 'url_main', 'url_email', 'url_remote_access'),
			(
				name,
				self._get_entry('company_new_description'),
				self._get_tag_from_combobox(self.gobjects['combobox_company_industry'], 'industries'),
				self._get_entry('company_url_main'),
				self._get_entry('company_url_email'),
				self._get_entry('company_url_remote_access')
			)
		)
		self.gobjects['radiobutton_company_existing'].set_active(True)
		return company_id

	def signal_assistant_apply(self, _):
		self._close_ready = False
		# have to do it this way because the next page will be selected when the apply signal is complete
		set_current_page = lambda page_name: self.assistant.set_current_page(max(0, self._page_titles[page_name] - 1))

		# get and validate the campaign name
		campaign_name = self.gobjects['entry_campaign_name'].get_text()
		campaign_name = campaign_name.strip()
		if not campaign_name:
			gui_utilities.show_dialog_error('Invalid Campaign Name', self.parent, 'A unique and valid campaign name must be specified.')
			set_current_page('Basic Settings')
			return True

		# validate the company
		company_id = None
		if self.gobjects['radiobutton_company_existing'].get_active():
			company_id = self._get_company_existing_id()
			if company_id is None:
				gui_utilities.show_dialog_error('Invalid Company', self.parent, 'A valid existing company must be specified.')
				set_current_page('Company')
				return True
		elif self.gobjects['radiobutton_company_new'].get_active():
			company_id = self._get_company_new_id()
			if company_id is None:
				gui_utilities.show_dialog_error('Invalid Company', self.parent, 'The new company settings are invalid.')
				set_current_page('Company')
				return True

		# get and validate the campaign expiration
		expiration = None
		if self.gobjects['checkbutton_expire_campaign'].get_property('active'):
			expiration = datetime.datetime.combine(
				gui_utilities.gtk_calendar_get_pydate(self.gobjects['calendar_campaign_expiration']),
				datetime.time(
					int(self.gobjects['spinbutton_campaign_expiration_hour'].get_value()),
					int(self.gobjects['spinbutton_campaign_expiration_minute'].get_value())
				)
			)
			expiration = utilities.datetime_local_to_utc(expiration)
			if self.is_new_campaign and expiration <= datetime.datetime.now():
				gui_utilities.show_dialog_error('Invalid Campaign Expiration', self.parent, 'The expiration date is set in the past.')
				set_current_page('Expiration')
				return True

		properties = {}

		# point of no return
		campaign_description = self._get_entry('campaign_description')
		if self.campaign_id:
			properties['name'] = self.campaign_name
			properties['description'] = campaign_description
			cid = self.campaign_id
		else:
			try:
				cid = self.application.rpc('campaign/new', campaign_name, description=campaign_description)
			except AdvancedHTTPServer.AdvancedHTTPServerRPCError as error:
				if not error.is_remote_exception:
					raise error
				if not error.remote_exception['name'] == 'exceptions.ValueError':
					raise error
				error_message = error.remote_exception.get('message', 'an unknown error occurred').capitalize() + '.'
				gui_utilities.show_dialog_error('Failed To Create Campaign', self.parent, error_message)
				set_current_page('Basic Settings')
				return True

		properties['campaign_type_id'] = self._get_tag_from_combobox(self.gobjects['combobox_campaign_type'], 'campaign_types')
		properties['company_id'] = company_id
		properties['expiration'] = expiration
		properties['reject_after_credentials'] = self.gobjects['checkbutton_reject_after_credentials'].get_property('active')
		self.application.rpc('db/table/set', 'campaigns', cid, properties.keys(), properties.values())

		should_subscribe = self.gobjects['checkbutton_alert_subscribe'].get_property('active')
		if should_subscribe != self.application.rpc('campaign/alerts/is_subscribed', cid):
			if should_subscribe:
				self.application.rpc('campaign/alerts/subscribe', cid)
			else:
				self.application.rpc('campaign/alerts/unsubscribe', cid)

		self.application.emit('campaign-changed', cid)
		self._close_ready = True
		return

	def signal_assistant_cancel(self, assistant):
		assistant.destroy()

	def signal_assistant_close(self, assistant):
		if self._close_ready:
			assistant.destroy()
		self._close_ready = True

	def signal_assistant_prepare(self, _, page):
		page_title = self.assistant.get_page_title(page)
		if page_title == 'Company':
			combobox = self.gobjects['combobox_company_existing']
			model = combobox.get_model()
			company_name = self.gobjects['entry_company_new_name'].get_text()
			if company_name:
				model_iter = gui_utilities.gtk_list_store_search(model, company_name, column=1)
				if model_iter is not None:
					combobox.set_active_iter(model_iter)
					self.gobjects['radiobutton_company_existing'].set_active(True)

	def signal_calendar_prev(self, calendar):
		today = datetime.date.today()
		calendar_day = gui_utilities.gtk_calendar_get_pydate(calendar)
		if calendar_day >= today:
			return
		gui_utilities.gtk_calendar_set_pydate(calendar, today)

	def signal_checkbutton_expire_campaign_toggled(self, _):
		active = self.gobjects['checkbutton_expire_campaign'].get_property('active')
		self.gobjects['frame_campaign_expiration'].set_sensitive(active)

	def signal_radiobutton_toggled(self, radiobutton):
		if not radiobutton.get_active():
			return
		if radiobutton == self.gobjects['radiobutton_company_existing']:
			self.gobjects['frame_company_existing'].set_sensitive(True)
			self.gobjects['frame_company_new'].set_sensitive(False)
		elif radiobutton == self.gobjects['radiobutton_company_new']:
			self.gobjects['frame_company_existing'].set_sensitive(False)
			self.gobjects['frame_company_new'].set_sensitive(True)
		elif radiobutton == self.gobjects['radiobutton_company_none']:
			self.gobjects['frame_company_existing'].set_sensitive(False)
			self.gobjects['frame_company_new'].set_sensitive(False)

	def interact(self):
		self.assistant.show_all()
