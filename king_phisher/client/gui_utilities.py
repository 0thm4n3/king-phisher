#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/gui_utilities.py
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

import contextlib
import datetime
import functools
import logging
import os
import socket
import threading

from king_phisher import find
from king_phisher import utilities

import boltons.strutils
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

GObject.type_register(GtkSource.View)

CALENDAR_DATE_FORMAT = '%b %d %Y'
GOBJECT_PROPERTY_MAP = {
	'calendar': None,  # delayed definition
	'checkbutton': 'active',
	'combobox': (
		lambda c, v: c.set_active_iter(gtk_list_store_search(c.get_model(), v)),
		lambda c: c.get_model().get_value(c.get_active_iter() or c.get_model().get_iter_first(), 0)
	),
	'entry': 'text',
	'spinbutton': 'value',
	'switch': 'active',
	'textview': (
		lambda t, v: t.get_buffer().set_text(v),
		lambda t: t.get_buffer().get_text(t.get_buffer().get_start_iter(), t.get_buffer().get_end_iter(), False)
	)
}
"""
The dictionary which maps GObjects to either the names of properties to
store text or a tuple which contains a set and get function. If a tuple
of two functions is specified the set function will be provided two
parameters, the object and the value and the get function will just be
provided the object.
"""

if isinstance(Gtk.Widget, utilities.Mock):
	_Gtk_CellRendererText = type('Gtk.CellRendererText', (object,), {})
	_Gtk_CellRendererText.__module__ = ''
	_Gtk_FileChooserDialog = type('Gtk.FileChooserDialog', (object,), {})
	_Gtk_FileChooserDialog.__module__ = ''
else:
	_Gtk_CellRendererText = Gtk.CellRendererText
	_Gtk_FileChooserDialog = Gtk.FileChooserDialog

def which_glade():
	"""
	Locate the glade data file which stores the UI information in a Gtk Builder
	format.

	:return: The path to the glade data file.
	:rtype: str
	"""
	return find.find_data_file(os.environ.get('KING_PHISHER_GLADE_FILE', 'king-phisher-client.ui'))

def glib_idle_add_wait(function, *args):
	"""
	Execute *function* in the main GTK loop using :py:func:`GLib.idle_add`
	and block until it has completed. This is useful for threads that need
	to update GUI data.

	:param function function: The function to call.
	:param args: The arguments to *functoin*.
	:return: The result of the function call.
	"""
	gsource_completed = threading.Event()
	results = []
	@functools.wraps(function)
	def wrapper():
		results.append(function(*args)) # pylint: disable=star-args
		gsource_completed.set()
		return False
	GLib.idle_add(wrapper)
	gsource_completed.wait()
	return results.pop()

def gobject_get_value(gobject, gtype=None):
	"""
	Retreive the value of a GObject widget. Only objects with value
	retrieving functions present in the :py:data:`.GOBJECT_PROPERTY_MAP`
	can be processed by this function.

	:param gobject: The object to retrieve the value for.
	:type gobject: :py:class:`GObject.Object`
	:param str gtype: An explicit type to treat *gobject* as.
	:return: The value of *gobject*.
	:rtype: str
	"""
	gtype = (gtype or gobject.__class__.__name__)
	gtype = gtype.lower()
	if isinstance(GOBJECT_PROPERTY_MAP[gtype], (list, tuple)):
		try:
			value = GOBJECT_PROPERTY_MAP[gtype][1](gobject)
		except AttributeError:
			return None
	else:
		value = gobject.get_property(GOBJECT_PROPERTY_MAP[gtype])
	return value

@contextlib.contextmanager
def gobject_signal_blocked(gobject, signal_name):
	"""
	This is a context manager that can be used with the 'with' statement
	to execute a block of code while *signal_name* is blocked.

	:param gobject: The object to block the signal on.
	:type gobject: :py:class:`GObject.Object`
	:param str signal_name: The name of the signal to block.
	"""
	signal_id = GObject.signal_lookup(signal_name, gobject.__class__)
	handler_id = GObject.signal_handler_find(gobject, GObject.SignalMatchType.ID, signal_id, 0, None, 0, 0)
	GObject.signal_handler_block(gobject, handler_id)
	yield
	GObject.signal_handler_unblock(gobject, handler_id)

def gtk_calendar_get_pydate(calendar):
	"""
	Get the Python date from a :py:class:`Gtk.Calendar` instance.

	:param calendar: The calendar to get the date from.
	:type calendar: :py:class:`Gtk.Calendar`
	:return: The date as returned by the calendar's :py:meth:`~Gtk.Calendar.get_date` method.
	:rtype: :py:class:`datetime.date`
	"""
	if not isinstance(calendar, Gtk.Calendar):
		raise ValueError('calendar must be a Gtk.Calendar instance')
	calendar_day = calendar.get_date()
	return datetime.date(calendar_day[0], calendar_day[1] + 1, calendar_day[2])

def gtk_calendar_set_pydate(calendar, pydate):
	"""
	Set the date on a :py:class:`Gtk.Calendar` instance from a Python
	:py:class:`datetime.date` object.

	:param calendar: The calendar to set the date for.
	:type calendar: :py:class:`Gtk.Calendar`
	:param pydate: The date to set on the calendar.
	:type pydate: :py:class:`datetime.date`
	"""
	calendar.select_month(pydate.month - 1, pydate.year)
	calendar.select_day(pydate.day)

GOBJECT_PROPERTY_MAP['calendar'] = (
	gtk_calendar_set_pydate,
	gtk_calendar_get_pydate
)

def gtk_list_store_search(list_store, value, column=0):
	"""
	Search a :py:class:`Gtk.ListStore` for a value and return a
	:py:class:`Gtk.TreeIter` to the first match.

	:param list_store: The list store to search.
	:type list_store: :py:class:`Gtk.ListStore`
	:param value: The value to search for.
	:param int column: The column in the row to check.
	:return: The row on which the value was found.
	:rtype: :py:class:`Gtk.TreeIter`
	"""
	for row in list_store:
		if row[column] == value:
			return row.iter
	return None

def gtk_menu_position(event, *args):
	"""
	Create a menu at the given location for an event. This function is meant to
	be used as the *func* parameter for the :py:meth:`Gtk.Menu.popup` method.
	The *event* object must be passed in as the first parameter, which can be
	accomplished using :py:func:`functools.partial`.

	:param event: The event to retrieve the coordinates for.
	"""
	if not hasattr(event, 'get_root_coords'):
		raise TypeError('event object has no get_root_coords method')
	coords = event.get_root_coords()
	return (coords[0], coords[1], True)

def gtk_style_context_get_color(sc, color_name, default=None):
	"""
	Look up a color by it's name in the :py:class:`Gtk.StyleContext` specified
	in *sc*, and return it as an :py:class:`Gdk.RGBA` instance if the color is
	defined. If the color is not found, *default* will be returned.

	:param sc: The style context to use.
	:type sc: :py:class:`Gtk.StyleContext`
	:param str color_name: The name of the color to lookup.
	:param default: The default color to return if the specified color was not found.
	:type default: str, :py:class:`Gdk.RGBA`
	:return: The color as an RGBA instance.
	:rtype: :py:class:`Gdk.RGBA`
	"""
	found, color_rgba = sc.lookup_color(color_name)
	if found:
		return color_rgba
	if isinstance(default, str):
		color_rgba = Gdk.RGBA()
		color_rgba.parse(default)
		return color_rgba
	elif isinstance(default, Gdk.RGBA):
		return default
	return

def gtk_sync():
	"""Wait while all pending GTK events are processed."""
	while Gtk.events_pending():
		Gtk.main_iteration()

def gtk_treesortable_sort_func_numeric(model, iter1, iter2, column_id):
	"""
	Sort the model by comparing text numeric values with place holders such as
	1,337. This is meant to be set as a sorting function using
	:py:meth:`Gtk.TreeSortable.set_sort_func`. The user_data parameter must be
	the column id which contains the numeric values to be sorted.

	:param model: The model that is being sorted.
	:type model: :py:class:`Gtk.TreeSortable`
	:param iter1: The iterator of the first item to compare.
	:type iter1: :py:class:`Gtk.TreeIter`
	:param iter2: The iterator of the second item to compare.
	:type iter2: :py:class:`Gtk.TreeIter`
	:param column_id: The ID of the column containing numeric values.
	:return: An integer, -1 if item1 should come before item2, 0 if they are the same and 1 if item1 should come after item2.
	:rtype: int
	"""
	column_id = column_id or 0
	item1 = model.get_value(iter1, column_id).replace(',', '')
	item2 = model.get_value(iter2, column_id).replace(',', '')
	if item1.isdigit() and item2.isdigit():
		return cmp(int(item1), int(item2))
	if item1.isdigit():
		return -1
	elif item2.isdigit():
		return 1
	item1 = model.get_value(iter1, column_id)
	item2 = model.get_value(iter2, column_id)
	return cmp(item1, item2)

def gtk_treeview_selection_to_clipboard(treeview, columns=0):
	"""
	Copy the currently selected values from the specified columns in the
	treeview to the users clipboard. If no value is selected in the treeview,
	then the clipboard is left unmodified. If multiple values are selected, they
	will all be placed in the clipboard on separate lines.

	:param treeview: The treeview instance to get the selection from.
	:type treeview: :py:class:`Gtk.TreeView`
	:param column: The column numbers to retrieve the value for.
	:type column: int, list, tuple
	"""
	treeview_selection = treeview.get_selection()
	(model, tree_paths) = treeview_selection.get_selected_rows()
	if not tree_paths:
		return
	if isinstance(columns, int):
		columns = (columns,)
	tree_iters = map(model.get_iter, tree_paths)
	selection_lines = []
	for ti in tree_iters:
		selection_lines.append(' '.join((model.get_value(ti, column) or '') for column in columns).strip())
	selection_lines = os.linesep.join(selection_lines)
	clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
	clipboard.set_text(selection_lines, -1)

def gtk_treeview_get_column_titles(treeview):
	"""
	Iterate over a GTK TreeView and return a tuple containing the id and title
	of each of it's columns.

	:param treeview: The treeview instance to retrieve columns from.
	:type treeview: :py:class:`Gtk.TreeView`
	"""
	for column_id, column in enumerate(treeview.get_columns()):
		column_name = column.get_title()
		yield (column_id, column_name)

def gtk_treeview_set_column_titles(treeview, column_titles, column_offset=0, renderers=None):
	"""
	Populate the column names of a GTK TreeView and set their sort IDs.

	:param treeview: The treeview to set column names for.
	:type treeview: :py:class:`Gtk.TreeView`
	:param list column_titles: The names of the columns.
	:param int column_offset: The offset to start setting column names at.
	:param list renderers: A list containing custom renderers to use for each column.
	:return: A dict of all the :py:class:`Gtk.TreeViewColumn` objects keyed by their column id.
	:rtype: dict
	"""
	columns = {}
	for column_id, column_title in enumerate(column_titles, column_offset):
		renderer = renderers[column_id - column_offset] if renderers else Gtk.CellRendererText()
		column = Gtk.TreeViewColumn(column_title, renderer, text=column_id)
		column.set_property('reorderable', True)
		column.set_sort_column_id(column_id)
		treeview.append_column(column)
		columns[column_id] = column
	return columns

def gtk_widget_destroy_children(widget):
	"""
	Destroy all GTK child objects of *widget*.

	:param widget: The widget to destroy all the children of.
	:type widget: :py:class:`Gtk.Widget`
	"""
	for child in widget.get_children():
		child.destroy()

def show_dialog(message_type, message, parent, secondary_text=None, message_buttons=Gtk.ButtonsType.OK):
	"""
	Display a dialog and return the response. The response is dependent on
	the value of *message_buttons*.

	:param message_type: The GTK message type to display.
	:type message_type: :py:class:`Gtk.MessageType`
	:param str message: The text to display in the dialog.
	:param parent: The parent window that the dialog should belong to.
	:type parent: :py:class:`Gtk.Window`
	:param str secondary_text: Optional subtext for the dialog.
	:param message_buttons: The buttons to display in the dialog box.
	:type message_buttons: :py:class:`Gtk.ButtonsType`
	:return: The response of the dialog.
	:rtype: int
	"""
	dialog = Gtk.MessageDialog(parent, Gtk.DialogFlags.DESTROY_WITH_PARENT, message_type, message_buttons, message)
	if secondary_text:
		dialog.format_secondary_text(secondary_text)
	dialog.show_all()
	response = dialog.run()
	dialog.destroy()
	return response

def show_dialog_error(*args, **kwargs):
	"""Display an error dialog with :py:func:`.show_dialog`."""
	return show_dialog(Gtk.MessageType.ERROR, *args, **kwargs)

def show_dialog_exc_socket_error(error, parent, title=None):
	"""
	Display an error dialog with details regarding a :py:exc:`socket.error`
	exception that has been raised.

	:param error: The exception instance that has been raised.
	:type error: :py:exc:`socket.error`
	:param parent: The parent window that the dialog should belong to.
	:type parent: :py:class:`Gtk.Window`
	:param title: The title of the error dialog that is displayed.
	"""
	title = title or 'Connection Error'
	if isinstance(error, socket.timeout):
		description = 'The connection to the server timed out.'
	else:
		error_number, error_message = error.args
		if error_number == 111:
			description = 'The server refused the connection.'
		else:
			description = "Socket error #{0} ({1}).".format((error_number or 'N/A'), error_message)
	return show_dialog(Gtk.MessageType.ERROR, title, parent, secondary_text=description)

def show_dialog_info(*args, **kwargs):
	"""Display an informational dialog with :py:func:`.show_dialog`."""
	return show_dialog(Gtk.MessageType.INFO, *args, **kwargs)

def show_dialog_warning(*args, **kwargs):
	"""Display an warning dialog with :py:func:`.show_dialog`."""
	return show_dialog(Gtk.MessageType.WARNING, *args, **kwargs)

def show_dialog_yes_no(*args, **kwargs):
	"""
	Display a dialog which asks a yes or no question with
	:py:func:`.show_dialog`.

	:return: True if the response is Yes.
	:rtype: bool
	"""
	kwargs['message_buttons'] = Gtk.ButtonsType.YES_NO
	return show_dialog(Gtk.MessageType.QUESTION, *args, **kwargs) == Gtk.ResponseType.YES

class CellRendererTextBytes(_Gtk_CellRendererText):
	"""A custom :py:class:`Gtk.CellRendererText` to render numeric values representing bytes."""
	def do_render(self, *args, **kwargs):
		original = self.get_property('text')
		if original.isdigit():
			self.set_property('text', boltons.strutils.bytes2human(int(original), 1))
		Gtk.CellRendererText.do_render(self, *args, **kwargs)

class GladeGObject(object):
	"""
	A base object to wrap GTK widgets loaded from Glade data files. This
	provides a number of convenience methods for managing the main widget
	and child widgets. This class is meant to be subclassed by classes
	representing objects from the Glade data file. The class names must
	be identical to the name of the object they represent in the Glade
	data file.
	"""
	gobject_ids = ()
	"""A tuple of unique children GTK Builder IDs to load from the Glade data file. These must be prefixed with their GTK type in all lowecase."""
	top_level_dependencies = ()
	"""Additional top level GObjects to load from the Glade data file."""
	config_prefix = ''
	"""A prefix to be used for keys when looking up value in the :py:attr:`~.GladeGObject.config`."""
	top_gobject = 'gobject'
	"""The name of the attribute to set a reference of the top level GObject to."""
	objects_persist = True
	"""Whether objects should be automatically loaded from and saved to the configuration."""
	def __init__(self, application):
		"""
		:param application: The parent application for this object.
		:type application: :py:class:`Gtk.Application`
		"""
		assert isinstance(application, Gtk.Application)
		self.config = application.config
		"""A reference to the King Phisher client configuration."""
		self.application = application
		"""The parent :py:class:`Gtk.Application` instance."""
		self.logger = logging.getLogger('KingPhisher.Client.' + self.__class__.__name__)

		builder = Gtk.Builder()
		self.gtk_builder = builder
		"""A :py:class:`Gtk.Builder` instance used to load Glade data with."""

		top_level_dependencies = [self.__class__.__name__]
		if self.top_level_dependencies is not None:
			top_level_dependencies.extend(self.top_level_dependencies)
		builder.add_objects_from_file(which_glade(), top_level_dependencies)
		builder.connect_signals(self)
		gobject = builder.get_object(self.__class__.__name__)
		if isinstance(gobject, Gtk.Window):
			gobject.set_transient_for(self.application.get_active_window())
			if isinstance(gobject, Gtk.ApplicationWindow):
				application.add_window(gobject)
			if isinstance(gobject, Gtk.Dialog):
				gobject.set_modal(True)
		setattr(self, self.top_gobject, gobject)

		self.gobjects = utilities.FreezableDict()
		"""A :py:class:`~king_phisher.utilities.FreezableDict` which maps gobjects to their unique GTK Builder id."""
		for gobject_id in self.gobject_ids:
			gobject = self.gtk_builder_get(gobject_id)
			# the following five lines ensure that the types match up, this is to enforce clean development
			gtype = gobject_id.split('_', 1)[0]
			if gobject is None:
				raise TypeError("gobject {0} could not be found in the glade file".format(gobject_id))
			elif gobject.__class__.__name__.lower() != gtype:
				raise TypeError("gobject {0} is of type {1} expected {2}".format(gobject_id, gobject.__class__.__name__, gtype))
			self.gobjects[gobject_id] = gobject
		self.gobjects.freeze()
		if self.objects_persist:
			self.objects_load_from_config()

	def destroy(self):
		"""Destroy the top-level GObject."""
		getattr(self, self.top_gobject).destroy()

	@property
	def parent(self):
		return self.application.get_active_window()

	def gtk_builder_get(self, gobject_id):
		"""
		Find the child GObject with name *gobject_id* from the GTK builder.

		:param str gobject_id: The object name to look for.
		:return: The GObject as found by the GTK builder.
		:rtype: :py:class:`GObject.Object`
		"""
		gtkbuilder_id = "{0}.{1}".format(self.__class__.__name__, gobject_id)
		self.logger.debug('loading GTK builder object with id: ' + gtkbuilder_id)
		return self.gtk_builder.get_object(gtkbuilder_id)

	def objects_load_from_config(self):
		"""
		Iterate through :py:attr:`.gobjects` and set the GObject's value
		from the corresponding value in the :py:attr:`~.GladeGObject.config`.
		"""
		for gobject_id, gobject in self.gobjects.items():
			gtype, config_name = gobject_id.split('_', 1)
			config_name = self.config_prefix + config_name
			if not gtype in GOBJECT_PROPERTY_MAP or not config_name in self.config:
				continue
			value = self.config[config_name]
			if value == None:
				continue
			if isinstance(GOBJECT_PROPERTY_MAP[gtype], (list, tuple)):
				GOBJECT_PROPERTY_MAP[gtype][0](gobject, value)
			else:
				gobject.set_property(GOBJECT_PROPERTY_MAP[gtype], value)

	def objects_save_to_config(self):
		for gobject_id, gobject in self.gobjects.items():
			gtype, config_name = gobject_id.split('_', 1)
			config_name = self.config_prefix + config_name
			if not gtype in GOBJECT_PROPERTY_MAP:
				continue
			self.config[config_name] = gobject_get_value(gobject, gtype)

class FileChooser(_Gtk_FileChooserDialog):
	"""Display a file chooser dialog."""
	def __init__(self, title, parent, **kwargs):
		"""
		:param str title: The title for the file chooser dialog.
		:param parent: The parent window for the dialog.
		:type parent: :py:class:`Gtk.Window`
		"""
		assert isinstance(parent, Gtk.Window)
		super(FileChooser, self).__init__(title, parent, **kwargs)
		self.parent = self.get_parent_window()

	def quick_add_filter(self, name, patterns):
		"""
		Add a filter for displaying files, this is useful in conjunction
		with :py:meth:`.run_quick_open`.

		:param str name: The name of the filter.
		:param patterns: The pattern(s) to match.
		:type patterns: list, str
		"""
		if not isinstance(patterns, (list, tuple)):
			patterns = (patterns,)
		new_filter = Gtk.FileFilter()
		new_filter.set_name(name)
		for pattern in patterns:
			new_filter.add_pattern(pattern)
		self.add_filter(new_filter)

	def run_quick_open(self):
		"""
		Display a dialog asking a user which file should be opened. The
		value of target_path in the returned dictionary is an absolute path.

		:return: A dictionary with target_uri and target_path keys representing the path choosen.
		:rtype: dict
		"""
		self.set_action(Gtk.FileChooserAction.OPEN)
		self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		self.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT)
		self.show_all()
		response = self.run()
		if response == Gtk.ResponseType.CANCEL:
			return None
		target_path = self.get_filename()
		if not os.access(target_path, os.R_OK):
			show_dialog_error('Can not read the selected file', self.parent)
			return None
		target_uri = self.get_uri()
		return {'target_uri': target_uri, 'target_path': target_path}

	def run_quick_save(self, current_name=None):
		"""
		Display a dialog which asks the user where a file should be saved. The
		value of target_path in the returned dictionary is an absolute path.

		:param set current_name: The name of the file to save.
		:return: A dictionary with target_uri and target_path keys representing the path choosen.
		:rtype: dict
		"""
		self.set_action(Gtk.FileChooserAction.SAVE)
		self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		self.add_button(Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT)
		self.set_do_overwrite_confirmation(True)
		if current_name:
			self.set_current_name(current_name)
		self.show_all()
		response = self.run()
		if response == Gtk.ResponseType.CANCEL:
			return None
		target_path = self.get_filename()
		if os.path.isfile(target_path):
			if not os.access(target_path, os.W_OK):
				show_dialog_error('Can not write to the selected file', self.parent)
				return None
		elif not os.access(os.path.dirname(target_path), os.W_OK):
			show_dialog_error('Can not create the selected file', self.parent)
			return None
		target_uri = self.get_uri()
		return {'target_uri': target_uri, 'target_path': target_path}

	def run_quick_select_directory(self):
		"""
		Display a dialog which asks the user to select a directory to use. The
		value of target_path in the returned dictionary is an absolute path.

		:return: A dictionary with target_uri and target_path keys representing the path chosen.
		:rtype: dict
		"""
		self.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
		self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		self.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT)
		self.show_all()
		response = self.run()
		if response == Gtk.ResponseType.CANCEL:
			return None
		target_uri = self.get_uri()
		target_path = self.get_filename()
		return {'target_uri': target_uri, 'target_path': target_path}

class FileMonitor(object):
	"""Monitor a file for changes."""
	def __init__(self, path, on_changed):
		"""
		:param str path: The path to monitor for changes.
		:param on_changed: The call back function to be called when changes are detected.
		:type on_changed: function
		"""
		self.logger = logging.getLogger('KingPhisher.Utility.FileMonitor')
		self.on_changed = on_changed
		self.path = path
		self._gfile = Gio.file_new_for_path(path)
		self._gfile_monitor = self._gfile.monitor(Gio.FileMonitorFlags.NONE, None)
		self._gfile_monitor.connect('changed', self.cb_changed)
		self.logger.debug('starting file monitor for: ' + path)

	def __del__(self):
		self.stop()

	def stop(self):
		"""Stop monitoring the file."""
		if self._gfile_monitor.is_cancelled():
			return
		self._gfile_monitor.cancel()
		self.logger.debug('cancelled file monitor for: ' + self.path)

	def cb_changed(self, gfile_monitor, gfile, gfile_other, gfile_monitor_event):
		self.logger.debug("file monitor {0} received event: {1}".format(self.path, gfile_monitor_event.value_name))
		self.on_changed(self.path, gfile_monitor_event)
