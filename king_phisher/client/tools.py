#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/tools.py
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

import code
import os
import pickle
import pty
import signal
import sys

from king_phisher.client.rpcclient import KingPhisherRPCClient

from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Vte

class KingPhisherClientRPCTerminal(object):
	def __init__(self, config, client):
		self.window = Gtk.Window()
		self.window.set_property('title', 'King Phisher RPC')
		self.window.set_transient_for(client)
		self.window.set_destroy_with_parent(True)
		self.window.connect('destroy', self.signal_window_destroy)
		self.terminal = Vte.Terminal()
		self.window.add(self.terminal)
		self.terminal.set_scroll_on_keystroke(True)

		rpc_data = pickle.dumps(client.rpc)
		child_pid, child_fd = pty.fork()
		if child_pid == 0:
			try:
				import readline
				import rlcompleter
			except ImportError:
				pass
			else:
				readline.parse_and_bind('tab: complete')
			rpc = pickle.loads(rpc_data)
			banner = "Python {0} on {1}".format(sys.version, sys.platform)
			print(banner)
			information = "Campaign Name: {0} ID: {1}".format(config['campaign_name'], config['campaign_id'])
			print(information)
			console_vars = {
				'CAMPAIGN_NAME': config['campaign_name'],
				'CAMPAIGN_ID': config['campaign_id'],
				'os':os,
				'rpc':rpc
			}
			export_to_builtins = ['CAMPAIGN_NAME', 'CAMPAIGN_ID', 'rpc']
			console = code.InteractiveConsole(console_vars)
			for var in export_to_builtins:
				console.push("__builtins__['{0}'] = {0}".format(var))
			console.interact('The \'rpc\' object holds the connected KingPhisherRPCClient instance')
			sys.exit(0)

		self.child_pid = child_pid
		vte_pty = Vte.Pty.new_foreign(child_fd)
		self.terminal.set_pty_object(vte_pty)
		GLib.child_watch_add(child_pid, lambda pid, status: self.window.destroy())
		self.window.show_all()

	def signal_window_destroy(self, window):
		if os.path.exists("/proc/{0}".format(self.child_pid)):
			os.kill(self.child_pid, signal.SIGKILL)
