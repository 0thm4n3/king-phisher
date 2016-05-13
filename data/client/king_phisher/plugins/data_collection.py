#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/plugins/data_collection.py
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

import argparse
import copy
import datetime
import hashlib
import sys

import king_phisher.color as color
import king_phisher.its as its
import king_phisher.json_ex as json_ex
import king_phisher.version as version
import king_phisher.client.plugins as plugins
import king_phisher.client.gui_utilities as gui_utilities
import king_phisher.client.widget.extras as extras

from smoke_zephyr.utilities import unique

__version__ = '1.0'

def generate_hash(data, algorithm='sha256'):
	if its.py_v3 and isinstance(data, str):
		data = data.encode('utf-8')
	return algorithm + ':' + hashlib.new(algorithm, data).hexdigest()

def generate_signature(data):
	data = copy.deepcopy(data)
	data['hash'] = None
	return generate_hash(json_ex.dumps(data))

def verify_signature(data):
	if not data.get('hash'):
		return False
	return data['hash'] == generate_signature(data)

class Plugin(plugins.ClientPlugin):
	version = __version__
	authors = ['Spencer McIntyre', 'Erik Daguerre']
	title = 'Anonymous Data Collection'
	description = """
	Generate anonymized data regarding the campaigns that have been run to
	submit to SecureState for collection and aggregation. Your submissions will
	help to fuel research into the effectiveness of phishing campaigns and user
	awareness. No identifying information regarding your campaigns will be
	collected.

	This plugin will generate a text file with the anonymous data. After the
	data file has been saved, please email it to king-phisher@securestate.com.
	If you would like credit when the research results are published, please
	include you or your companies attribution information.

	We greatly appreciate your data contributions to the King Phisher project!
	"""
	homepage = 'https://github.com/securestate/king-phisher'
	options = [
		plugins.ClientOptionInteger(
			'cycle_days',
			'Number of days between reminders to submit data.',
			default=90,
			display_name='Cycle in Days'
		)
	]

	def initialize(self):
		self.signal_connect('server-connected', self.signal_server_connected)
		return True

	def signal_server_connected(self, _):
		config = self.config
		if 'last_data' in config and datetime.datetime.utcnow() - config['last_date'] < datetime.timedelta(days=config['cycle_days']):
			return
		dialog_txt = 'Would you like to generate research data to submit to SecureState?'
		if not gui_utilities.show_dialog_yes_no('Phishing Data Collection', self.application.get_active_window(), dialog_txt):
			return

		get_stats = StatsGenerator(self.application.rpc)
		stats = get_stats.generate_stats()

		dialog = extras.FileChooserDialog('Save Anonymized Data', self.application.get_active_window())
		file_name = 'anonymized_phishing_data.txt'
		response = dialog.run_quick_save(file_name)
		dialog.destroy()
		if not response['target_path']:
			return
		with open(response['target_path'], 'w') as file_h:
			file_h.write(stats)
		gui_utilities.show_dialog_info(
			'Successfully Generated Data',
			self.application.get_active_window(),
			"Please review and email:\n{}\nto king-phisher@securestate.com".format(response['target_path'])
		)
		config['last_date'] = datetime.datetime.utcnow()

class StatsGenerator(object):
	def __init__(self, rpc):
		self.rpc = rpc

	def generate_stats(self):
		stats = {
			'campaigns': [],
			'generated': datetime.datetime.utcnow(),
			'version': {
				'king_phisher': version.distutils_version,
				'stats': __version__
			}
		}
		rpc = self.rpc
		for campaign in rpc.remote_table('campaigns'):
			stats['campaigns'].append(self._campaign_stats(campaign))
		stats['hash'] = generate_signature(stats)
		return json_ex.dumps(stats)

	def _campaign_stats(self, campaign):
		rpc = self.rpc
		messages = list(rpc.remote_table('messages', query_filter={'campaign_id': campaign.id}))
		visits = list(rpc.remote_table('visits', query_filter={'campaign_id': campaign.id}))
		credentials = list(rpc.remote_table('credentials', query_filter={'campaign_id': campaign.id}))
		stats = {
			'created': campaign.created,
			'expiration': campaign.expiration,
			'reject_after_credentials': campaign.reject_after_credentials,
			'id': campaign.id,
			'name': generate_hash(campaign.name),
			'messages': {
				'total': len(messages),
				'unique': {
					'by_target': len(unique(messages, key=lambda message: message.target_email)),
				}
			},
			'visits': {
				'total': len(visits),
				'unique': {
					'by_message': len(unique(visits, key=lambda visit: visit.message_id)),
				}
			},
			'credentials': {
				'total': len(credentials),
				'unique': {
					'by_message': len(unique(credentials, key=lambda credential: credential.message_id)),
					'by_visit': len(unique(credentials, key=lambda credential: credential.visit_id))
				}
			}
		}
		return stats

def main():
	parser = argparse.ArgumentParser(description='Stat File Verification', conflict_handler='resolve')
	parser.add_argument('-v', '--version', action='version', version='%(prog)s Version: ' + __version__)
	parser.add_argument('data_file', type=argparse.FileType('r'), help='the stats file to verify')
	arguments = parser.parse_args()

	try:
		data = json_ex.load(arguments.data_file)
	except Exception:
		color.print_error('failed to load the data')
		return 1
	else:
		color.print_status('loaded the statistics data')
	finally:
		arguments.data_file.close()

	if not verify_signature(data):
		color.print_error('the signature is invalid')
		return 1

	color.print_good('the signature is valid')
	return 0

if __name__ == '__main__':
	sys.exit(main())
