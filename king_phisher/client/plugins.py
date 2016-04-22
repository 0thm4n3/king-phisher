#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/plugins.py
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

import weakref

from king_phisher import plugins

class ClientPlugin(plugins.PluginBase):
	"""
	The base object to be inherited by plugins that are loaded into the King
	Phisher client. This provides a convenient interface for interacting with
	the runtime.
	"""
	_logging_prefix = 'KingPhisher.Plugins.Client.'
	def __init__(self, application):
		super(ClientPlugin, self).__init__()
		self.application = application
		"""A reference to the :py:class:`~king_phisher.client.application.KingPhisherClientApplication`."""
		self._signals = []

	def _cleanup(self):
		while self._signals:
			ref, handler_id = self._signals.pop()
			gobject = ref()
			if gobject is None:
				continue
			gobject.disconnect(handler_id)

	@property
	def config(self):
		"""
		A dictionary that can be used by this plugin for persistent storage of it's configuration.
		"""
		config = self.application.config['plugins'].get(self.name)
		if config is None:
			config = {}
			self.application.config['plugins'][self.name] = config
		return config

	def signal_connect(self, name, handler, gobject=None):
		"""
		Connect *handler* to a signal by *name* to an arbitrary GObject. Signals
		connected through this method are automatically cleaned up when the
		plugin is disabled. If not GObject is specified, the application is
		used.

		.. warning::
			If the signal needs to be disconnected manually by the plugin, this
			method should not be used. Instead the handler id should be kept as
			returned by the GObject's native connect method.

		:param str name: The name of the signal.
		:param handler: The function to be invoked with the signal is emitted.
		:type handler: function
		:param gobject: The object to connect the signal to.
		"""
		gobject = gobject or self.application
		handler_id = gobject.connect(name, handler)
		self._signals.append((weakref.ref(gobject), handler_id))

class ClientPluginManager(plugins.PluginManagerBase):
	"""
	The manager for plugins loaded into the King Phisher client application.
	"""
	_plugin_klass = ClientPlugin
	def __init__(self, path, application):
		super(ClientPluginManager, self).__init__(path, (application,))
