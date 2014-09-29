#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/graphs.py
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

import time

from king_phisher import ua_parser
from king_phisher import utilities
from king_phisher.client import gui_utilities

from gi.repository import Gtk

try:
	import matplotlib
except ImportError:
	has_matplotlib = False
	"""Whether the :py:mod:`matplotlib` module is available."""
else:
	has_matplotlib = True
	matplotlib.rcParams['backend'] = 'TkAgg'
	from matplotlib import dates
	from matplotlib import pyplot
	from matplotlib.figure import Figure
	from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
	from matplotlib.backends.backend_gtk3agg import FigureManagerGTK3Agg as FigureManager
	from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar

EXPORTED_GRAPHS = {}

def export(klass):
	"""
	Decorator for classes to mark them as valid graph providers.

	:param class klass: The class to mark as a graph provider.
	:return: The *klass* parameter is returned.
	"""
	graph_name = klass.__name__[13:]
	klass._graph_id = len(EXPORTED_GRAPHS)
	klass.name = graph_name
	EXPORTED_GRAPHS[graph_name] = klass
	return klass

def get_graph(graph_name):
	"""
	Return the graph providing class for *graph_name*.

	:param str graph_name: The name of the graph provider.
	:return: The graph provider class.
	:rtype: :py:class:`.CampaignGraph`
	"""
	return EXPORTED_GRAPHS.get(graph_name)

def get_graphs():
	"""
	Get a list of all registered graph providers.

	:return: All registered graph providers.
	:rtype: list
	"""
	return sorted(EXPORTED_GRAPHS.keys())

class CampaignGraph(object):
	"""
	A basic graph provider for using :py:mod:`matplotlib` to create graph
	representations of campaign data. This class is meant to be subclassed
	by real providers.
	"""
	title = 'Unknown'
	"""The title of the graph."""
	_graph_id = None
	table_subscriptions = []
	"""A list of tables from which information is needed to produce the graph."""
	def __init__(self, config, parent, size_request=None):
		"""
		:param dict config: The King Phisher client configuration.
		:param parent: The parent window for this object.
		:type parent: :py:class:`Gtk.Window`
		:param tuple size_request: The size to set for the canvas.
		"""
		self.config = config
		"""A reference to the King Phisher client configuration."""
		self.parent = parent
		"""The parent :py:class:`Gtk.Window` instance."""
		self.figure, ax = pyplot.subplots()
		self.axes = self.figure.get_axes()
		self.canvas = FigureCanvas(self.figure)
		self.manager = None
		if size_request:
			self.canvas.set_size_request(*size_request)
		self.canvas.mpl_connect('button_press_event', self.mpl_signal_canvas_button_pressed)
		self.canvas.show()
		self.navigation_toolbar = NavigationToolbar(self.canvas, self.parent)
		self.navigation_toolbar.hide()
		self.popup_menu = Gtk.Menu.new()

		menu_item = Gtk.MenuItem.new_with_label('Export')
		menu_item.connect('activate', self.signal_activate_popup_menu_export)
		self.popup_menu.append(menu_item)

		menu_item = Gtk.MenuItem.new_with_label('Refresh')
		menu_item.connect('activate', lambda action: self.refresh())
		self.popup_menu.append(menu_item)

		menu_item = Gtk.CheckMenuItem.new_with_label('Show Toolbar')
		menu_item.connect('toggled', self.signal_toggled_popup_menu_show_toolbar)
		self.popup_menu.append(menu_item)
		self.popup_menu.show_all()

	@classmethod
	def get_graph_id(klass):
		"""
		The graph id of an exported :py:class:`.CampaignGraph`.

		:param klass: The class to return the graph id of.
		:type klass: :py:class:`.CampaignGraph`
		:return: The id of the graph.
		:rtype: int
		"""
		return klass._graph_id

	def make_window(self):
		"""
		Create a window from the figure manager.

		:return: The graph in a new, dedicated window.
		:rtype: :py:class:`Gtk.Window`
		"""
		if self.manager == None:
			self.manager = FigureManager(self.canvas, 0)
		window = self.manager.window
		window.set_transient_for(self.parent)
		window.set_title(self.title)
		return window

	def mpl_signal_canvas_button_pressed(self, event):
		if event.button != 3:
			return
		pos_func = lambda m, d: (event.x, event.y, True)
		self.popup_menu.popup(None, None, None, None, event.button, Gtk.get_current_event_time())
		return True

	def signal_activate_popup_menu_export(self, action):
		dialog = gui_utilities.UtilityFileChooser('Export Graph', self.parent)
		file_name = self.config['campaign_name'] + '.png'
		response = dialog.run_quick_save(file_name)
		dialog.destroy()
		if not response:
			return
		destination_file = response['target_path']
		self.figure.savefig(destination_file, format='png')

	def signal_toggled_popup_menu_show_toolbar(self, widget):
		if widget.get_property('active'):
			self.navigation_toolbar.show()
		else:
			self.navigation_toolbar.hide()

	def load_graph(self):
		"""Load the graph information via :py:meth:`.refresh`."""
		self.refresh()

	def refresh(self, info_cache=None):
		"""
		Refresh the graph data by retrieving the information from the
		remote server.

		:param dict info_cache: An optional cache of data tables.
		:return: A dictionary of cached tables from the server.
		:rtype: dict
		"""
		info_cache = (info_cache or {})
		if not self.parent.rpc:
			return info_cache
		for table in self.table_subscriptions:
			if not table in info_cache:
				info_cache[table] = list(self.parent.rpc.remote_table('campaign/' + table, self.config['campaign_id']))
		map(lambda ax: ax.clear(), self.axes)
		self._load_graph(info_cache)
		self.canvas.draw()
		return info_cache

@export
class CampaignGraphOverview(CampaignGraph):
	"""Display a graph which represents an overview of the campaign."""
	title = 'Overview'
	table_subscriptions = ['credentials', 'visits']
	def _load_graph(self, info_cache):
		rpc = self.parent.rpc
		cid = self.config['campaign_id']

		visits = info_cache['visits']
		creds = info_cache['credentials']

		bars = []
		bars.append(rpc('campaign/messages/count', cid))
		bars.append(len(visits))
		bars.append(len(utilities.unique(visits, key=lambda visit: visit['message_id'])))
		if len(creds):
			bars.append(len(creds))
			bars.append(len(utilities.unique(creds, key=lambda cred: cred['message_id'])))
		width = 0.25
		ax = self.axes[0]
		bars = ax.bar(range(len(bars)), bars, width)
		ax.set_ylabel('Grand Total')
		ax.set_title('Campaign Overview')
		ax.set_xticks(map(lambda x: float(x) + (width / 2), range(len(bars))))
		ax.set_xticklabels(('Messages', 'Visits', 'Unique\nVisits', 'Credentials', 'Unique\nCredentials')[:len(bars)], rotation=30)
		for col in bars:
			height = col.get_height()
			ax.text(col.get_x() + col.get_width() / 2.0, height, str(height), ha='center', va='bottom')
		self.figure.subplots_adjust(bottom=0.25)
		return info_cache

@export
class CampaignGraphVisitorInfo(CampaignGraph):
	"""Display a graph which represents information regarding a campaign's visitors."""
	title = 'Visitor Information'
	table_subscriptions = ['visits']
	def _load_graph(self, info_cache):
		rpc = self.parent.rpc
		cid = self.config['campaign_id']
		visits = info_cache['visits']

		operating_systems = {}
		unknown_os = 'Unknown OS'
		for visit in visits:
			user_agent = ua_parser.parse_user_agent(visit['visitor_details'])
			if user_agent:
				operating_systems[user_agent.os_name] = operating_systems.get(user_agent.os_name, 0) + 1
			else:
				operating_systems[unknown_os] = operating_systems.get(unknown_os, 0) + 1
		os_names = operating_systems.keys()
		os_names.sort(key=lambda name: operating_systems[name])
		os_names.reverse()

		bars = []
		for os_name in os_names:
			bars.append(operating_systems[os_name])
		width = 0.25
		ax = self.axes[0]
		bars = ax.bar(range(len(bars)), bars, width)
		ax.set_ylabel('Total Visits')
		ax.set_title('Visitor OS Information')
		ax.set_xticks(map(lambda x: float(x) + (width / 2), range(len(bars))))
		ax.set_xticklabels(os_names, rotation=30)
		for col in bars:
			height = col.get_height()
			ax.text(col.get_x() + col.get_width() / 2.0, height, str(height), ha='center', va='bottom')
		self.figure.subplots_adjust(bottom=0.25)
		return info_cache

@export
class CampaignGraphVisitsTimeline(CampaignGraph):
	"""Display a graph which represents the visits of a campaign over time."""
	title = 'Visits Timeline'
	table_subscriptions = ['visits']
	def _load_graph(self, info_cache):
		rpc = self.parent.rpc
		cid = self.config['campaign_id']
		visits = info_cache['visits']
		first_visits = map(lambda visit: visit['first_visit'], visits)
		first_visits.sort()

		ax = self.axes[0]
		if len(first_visits):
			ax.plot_date(first_visits, range(1, len(first_visits) + 1), '-')
			self.figure.autofmt_xdate()
		ax.set_ylabel('Number of Visits')
		ax.set_title('Visits Over Time')
		ax.xaxis.set_major_locator(dates.DayLocator())
		ax.xaxis.set_major_formatter(dates.DateFormatter('%Y-%m-%d'))
		ax.xaxis.set_minor_locator(dates.HourLocator())
		ax.autoscale_view()
		ax.fmt_xdata = dates.DateFormatter('%Y-%m-%d')
		return info_cache
