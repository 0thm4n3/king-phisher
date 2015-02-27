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

import collections
import datetime
import string
import sys

from king_phisher import ua_parser
from king_phisher import utilities
from king_phisher.client import gui_utilities

from gi.repository import Gtk
from smoke_zephyr.requirements import check_requirements

try:
	import matplotlib
	matplotlib.rcParams['backend'] = 'GTK3Cairo'
	from matplotlib import dates
	from matplotlib import pyplot
	from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
	from matplotlib.backends.backend_gtk3cairo import FigureManagerGTK3Cairo as FigureManager
	from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar
except ImportError:
	has_matplotlib = False
	"""Whether the :py:mod:`matplotlib` module is available."""
else:
	if not getattr(sys, 'frozen', False) and check_requirements(['matplotlib>=1.4.1']):
		has_matplotlib = False
	else:
		has_matplotlib = True

try:
	import mpl_toolkits.basemap
except ImportError:
	has_matplotlib_basemap = False
	"""Whether the :py:mod:`mpl_toolkits.basemap` module is available."""
else:
	if not getattr(sys, 'frozen', False) and check_requirements(['basemap>=1.0.7']):
		has_matplotlib_basemap = False
	else:
		has_matplotlib_basemap = True

EXPORTED_GRAPHS = {}

__all__ = ['export_graph_provider', 'get_graph', 'get_graphs', 'CampaignGraph']
_mpl_os_colors = {
	'Android': 'olive',
	'BlackBerry': 'gray',
	'iOS': 'violet',
	'Linux': 'palegreen',
	'OS X': 'darkviolet',
	'Windows NT': 'gold'
}

def export_graph_provider(cls):
	"""
	Decorator to mark classes as valid graph providers. This decorator also sets
	the :py:attr:`~.CampaignGraph.name` attribute.

	:param class cls: The class to mark as a graph provider.
	:return: The *cls* parameter is returned.
	"""
	if not issubclass(cls, CampaignGraph):
		raise RuntimeError("{0} is not a subclass of CampaignGraph".format(cls.__name__))
	if not cls.is_available:
		return None
	graph_name = cls.__name__[13:]
	cls.name = graph_name
	EXPORTED_GRAPHS[graph_name] = cls
	return cls

def get_graph(graph_name):
	"""
	Return the graph providing class for *graph_name*. The class providing the
	specified graph must have been previously exported using
	:py:func:`.export_graph_provider`.

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
	name = 'Unknown'
	"""The name of the graph provider."""
	name_human = 'Unknown'
	"""The human readable name of the graph provider used for UI identification."""
	graph_title = 'Unknown'
	"""The title that will be given to the graph."""
	table_subscriptions = []
	"""A list of tables from which information is needed to produce the graph."""
	is_available = True
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
		self.figure, _ = pyplot.subplots()
		self.axes = self.figure.get_axes()
		self.canvas = FigureCanvas(self.figure)
		self.manager = None
		if size_request:
			self.canvas.set_size_request(*size_request)
		self.canvas.mpl_connect('button_press_event', self.mpl_signal_canvas_button_pressed)
		self.canvas.show()
		self.navigation_toolbar = NavigationToolbar(self.canvas, self.parent)
		self.popup_menu = Gtk.Menu.new()

		menu_item = Gtk.MenuItem.new_with_label('Export')
		menu_item.connect('activate', self.signal_activate_popup_menu_export)
		self.popup_menu.append(menu_item)

		menu_item = Gtk.MenuItem.new_with_label('Refresh')
		menu_item.connect('activate', lambda action: self.refresh())
		self.popup_menu.append(menu_item)

		menu_item = Gtk.CheckMenuItem.new_with_label('Show Toolbar')
		menu_item.connect('toggled', self.signal_toggled_popup_menu_show_toolbar)
		self._menu_item_show_toolbar = menu_item
		self.popup_menu.append(menu_item)
		self.popup_menu.show_all()
		self.navigation_toolbar.hide()

	def _load_graph(self, info_cache):
		raise NotImplementedError()

	def _null_graph_pie(self, title):
		ax = self.axes[0]
		ax.pie((100,), labels=(title,), colors=('skyblue',), autopct='%1.0f%%', shadow=True, startangle=90)
		ax.axis('equal')
		return

	def make_window(self):
		"""
		Create a window from the figure manager.

		:return: The graph in a new, dedicated window.
		:rtype: :py:class:`Gtk.Window`
		"""
		if self.manager == None:
			self.manager = FigureManager(self.canvas, 0)
		self.navigation_toolbar.destroy()
		self.navigation_toolbar = self.manager.toolbar
		self._menu_item_show_toolbar.set_active(True)
		window = self.manager.window
		window.set_transient_for(self.parent)
		window.set_title(self.graph_title)
		return window

	def mpl_signal_canvas_button_pressed(self, event):
		if event.button != 3:
			return
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

	def refresh(self, info_cache=None, stop_event=None):
		"""
		Refresh the graph data by retrieving the information from the
		remote server.

		:param dict info_cache: An optional cache of data tables.
		:param stop_event: An optional object indicating that the operation should stop.
		:type stop_event: :py:class:`threading.Event`
		:return: A dictionary of cached tables from the server.
		:rtype: dict
		"""
		info_cache = (info_cache or {})
		if not self.parent.rpc:
			return info_cache
		for table in self.table_subscriptions:
			if stop_event and stop_event.is_set():
				return info_cache
			if not table in info_cache:
				info_cache[table] = list(self.parent.rpc.remote_table('campaign/' + table, self.config['campaign_id']))
		for ax in self.axes:
			ax.clear()
		self._load_graph(info_cache)
		self.axes[0].set_title(self.graph_title, y=1.03)
		self.canvas.draw()
		return info_cache

@export_graph_provider
class CampaignGraphOverview(CampaignGraph):
	"""Display a graph which represents an overview of the campaign."""
	graph_title = 'Campaign Overview'
	name_human = 'Bar - Campaign Overview'
	table_subscriptions = ('credentials', 'visits')
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
		top_lim = max(bars)
		top_lim += 5 - top_lim % 5
		width = 0.25
		ax = self.axes[0]
		bars = ax.bar(range(len(bars)), bars, width)
		ax.set_ylabel('Grand Total')
		ax.set_yticks((1, top_lim / 2, top_lim))
		ax.set_xticks([float(x) + (width / 2) for x in range(len(bars))])
		ax.set_xticklabels(('Messages', 'Visits', 'Unique\nVisits', 'Credentials', 'Unique\nCredentials')[:len(bars)], rotation=30)
		ax.set_ylim(top=top_lim)
		for col in bars:
			height = col.get_height()
			ax.text(col.get_x() + col.get_width() / 2.0, height, str(height), ha='center', va='bottom')
		self.figure.subplots_adjust(bottom=0.25)
		return

@export_graph_provider
class CampaignGraphVisitorInfo(CampaignGraph):
	"""Display a graph which shows the different operating systems seen from visitors."""
	graph_title = 'Campaign Visitor OS Information'
	name_human = 'Bar - Visitor OS Information'
	table_subscriptions = ('visits',)
	def _load_graph(self, info_cache):
		visits = info_cache['visits']

		operating_systems = collections.Counter()
		operating_systems.update([ua_parser.parse_user_agent(visit['visitor_details']).os_name or 'Unknown OS' for visit in visits])
		os_names = list(operating_systems.keys())
		os_names.sort(key=lambda name: operating_systems[name])
		os_names.reverse()

		bars = []
		for os_name in os_names:
			bars.append(operating_systems[os_name])
		colors = [_mpl_os_colors.get(osn, 'skyblue') for osn in os_names]
		width = 0.25
		ax = self.axes[0]
		bars = ax.bar(range(len(bars)), bars, width, color=colors)
		top_lim = max(os for os in operating_systems.values())
		top_lim += 5 - top_lim % 5
		ax.set_ylabel('Total Visits')
		ax.set_yticks((1, top_lim / 2, top_lim))
		ax.set_xticks([float(x) + (width / 2) for x in range(len(bars))])
		ax.set_xticklabels(os_names, rotation=30)
		ax.set_ylim(top=top_lim)
		for col in bars:
			height = col.get_height()
			ax.text(col.get_x() + col.get_width() / 2.0, height, str(height), ha='center', va='bottom')
		self.figure.subplots_adjust(bottom=0.25)
		return

@export_graph_provider
class CampaignGraphVisitorInfoPie(CampaignGraph):
	"""Display a graph which compares the different operating systems seen from visitors."""
	graph_title = 'Campaign Visitor OS Information'
	name_human = 'Pie - Visitor OS Information'
	table_subscriptions = ('visits',)
	def _load_graph(self, info_cache):
		visits = info_cache['visits']
		if not len(visits):
			self._null_graph_pie('No Visitor Information')
			return

		operating_systems = collections.Counter()
		operating_systems.update([ua_parser.parse_user_agent(visit['visitor_details']).os_name or 'Unknown OS' for visit in visits])
		(os_names, count) = zip(*operating_systems.items())
		colors = [_mpl_os_colors.get(osn, 'skyblue') for osn in os_names]

		ax = self.axes[0]
		ax.pie(count, labels=os_names, labeldistance=1.05, colors=colors, autopct='%1.1f%%', shadow=True, startangle=45)
		ax.axis('equal')
		return

@export_graph_provider
class CampaignGraphVisitsTimeline(CampaignGraph):
	"""Display a graph which represents the visits of a campaign over time."""
	graph_title = 'Campaign Visits Timeline'
	name_human = 'Line - Visits Timeline'
	table_subscriptions = ('visits',)
	def _load_graph(self, info_cache):
		visits = info_cache['visits']
		first_visits = [visit['first_visit'] for visit in visits]

		ax = self.axes[0]
		ax.set_ylabel('Number of Visits')
		if not len(first_visits):
			ax.set_yticks((0,))
			ax.set_xticks((0,))
			return

		ax.xaxis.set_major_locator(dates.AutoDateLocator())
		ax.xaxis.set_major_formatter(dates.DateFormatter('%Y-%m-%d'))
		first_visits.sort()
		first_visit_span = first_visits[-1] - first_visits[0]
		ax.plot_date(first_visits, range(1, len(first_visits) + 1), '-')
		self.figure.autofmt_xdate()
		if first_visit_span < datetime.timedelta(7):
			ax.xaxis.set_minor_locator(dates.DayLocator())
			if first_visit_span < datetime.timedelta(3) and len(first_visits) > 1:
				ax.xaxis.set_minor_locator(dates.HourLocator())
		ax.grid(True)
		return

@export_graph_provider
class CampaignGraphMessageResults(CampaignGraph):
	"""Display the percentage of messages which resulted in a visit."""
	graph_title = 'Campaign Message Results'
	name_human = 'Pie - Message Results'
	table_subscriptions = ('credentials', 'visits')
	def _load_graph(self, info_cache):
		rpc = self.parent.rpc
		cid = self.config['campaign_id']

		messages_count = rpc('campaign/messages/count', cid)
		if not messages_count:
			self._null_graph_pie('No Messages Sent')
			return
		visits_count = len(utilities.unique(info_cache['visits'], key=lambda visit: visit['message_id']))
		credentials_count = len(utilities.unique(info_cache['credentials'], key=lambda cred: cred['message_id']))

		assert credentials_count <= visits_count <= messages_count
		labels = ['Without Visit', 'With Visit', 'With Credentials']
		sizes = []
		sizes.append((float(messages_count - visits_count) / float(messages_count)) * 100)
		sizes.append((float(visits_count - credentials_count) / float(messages_count)) * 100)
		sizes.append((float(credentials_count) / float(messages_count)) * 100)
		colors = ['yellowgreen', 'gold', 'lightcoral']
		explode = [0.1, 0, 0]
		if not credentials_count:
			labels.pop()
			sizes.pop()
			colors.pop()
			explode.pop()
		if not visits_count:
			labels.pop()
			sizes.pop()
			colors.pop()
			explode.pop()
		ax = self.axes[0]
		ax.pie(sizes, explode=explode, labels=labels, labeldistance=1.05, colors=colors, autopct='%1.1f%%', shadow=True, startangle=45)
		ax.axis('equal')
		return

@export_graph_provider
class CampaignGraphVisitsMap(CampaignGraph):
	"""Display a map which shows the locations of visit origins."""
	graph_title = 'Campaign Visit Locations Map'
	name_human = 'Map - Visit Locations'
	table_subscriptions = ['visits']
	is_available = has_matplotlib_basemap
	def _load_graph(self, info_cache):
		visits = utilities.unique(info_cache['visits'], key=lambda visit: visit['message_id'])

		ax = self.axes[0]
		bm = mpl_toolkits.basemap.Basemap(projection='kav7', lon_0=0, resolution='c', ax=ax)

		bm.drawcoastlines()
		bm.drawcountries()
		bm.fillcontinents(color='gray', lake_color='aqua')
		bm.drawparallels((-60, -30, 0, 30, 60), labels=(1, 1, 0, 0))
		bm.drawmeridians((0, 90, 180, 270), labels=(0, 0, 0, 1))
		bm.drawmapboundary(fill_color='aqua')

		ctr = collections.Counter()
		ctr.update([visit['visitor_ip'] for visit in visits])

		for visitor_ip, occurances in ctr.items():
			geo_location = self.parent.rpc.geoip_lookup(visitor_ip)
			xpt, ypt = bm(geo_location.coordinates.longitude, geo_location.coordinates.latitude)
			bm.plot(xpt, ypt, 'o', markerfacecolor='gold', markersize=float(min(15, occurances)))
		return info_cache

@export_graph_provider
class CampaignGraphPasswordComplexityPie(CampaignGraph):
	"""Display a graph which displays the number of passwords which meet standard complexity requirements."""
	graph_title = 'Campaign Password Complexity'
	name_human = 'Pie - Password Complexity'
	table_subscriptions = ('credentials',)
	def _load_graph(self, info_cache):
		passwords = set(cred['password'] for cred in info_cache['credentials'])
		if not len(passwords):
			self._null_graph_pie('No Credential Information')
			return
		ctr = collections.Counter()
		ctr.update(self._check_complexity(password) for password in passwords)

		ax = self.axes[0]
		ax.pie((ctr[True], ctr[False]), labels=('Complex', 'Not Complex'), labeldistance=1.05, colors=('yellowgreen', 'lightcoral'), autopct='%1.1f%%', shadow=True, startangle=45)
		ax.axis('equal')
		return

	def _check_complexity(self, password):
		if len(password) < 8:
			return False
		met = 0
		for char_set in (string.ascii_uppercase, string.ascii_lowercase, string.digits, string.punctuation):
			for char in password:
				if char in char_set:
					met += 1
					break
		return met >= 3
