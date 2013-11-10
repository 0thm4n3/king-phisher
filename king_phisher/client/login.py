from gi.repository import Gtk

from king_phisher.utilities import UtilityGladeGObject

class KingPhisherClientLoginDialog(UtilityGladeGObject):
	gobject_ids = [
		'entry_server',
		'entry_server_username',
		'entry_server_password'
	]
	gobject_id_suffix = 1
	top_gobject = 'dialog'

	def interact(self):
		self.dialog.show_all()
		response = self.dialog.run()
		if response != Gtk.ResponseType.CANCEL:
			self.objects_save_to_config()
		self.dialog.destroy()
		return response

class KingPhisherClientSSHLoginDialog(KingPhisherClientLoginDialog):
	gobject_ids = [
		'entry_ssh_server',
		'entry_ssh_username',
		'entry_ssh_password'
	]
