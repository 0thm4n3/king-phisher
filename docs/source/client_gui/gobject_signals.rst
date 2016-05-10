GObject Signals
===============

.. _gobject-signals-application-label:

KingPhisherClientApplication Signals
------------------------------------

The following are the signals for the
:py:class:`~king_phisher.client.application.KingPhisherClientApplication`
object. These signals can be used by the client API to subscribe to specific
events.

.. py:function:: campaign-changed(campaign_id)

   This signal is emitted when campaign attributes are changed. Subscribers to
   this signal can use it to update and refresh information for the modified
   campaign.
   Signal emission stage set to run first.

   :Emission Stage: ``RUN_FIRST``
   :param str campaign_id: The ID of the campaign whose information was changed.

.. py:function:: campaign-created(campaign_id)

   This signal is emitted after the user creates a new campaign id. Subscribers
   to this signal can use it to conduct an action after a new campaign id is created.

   :Emission Stage: ``RUN_FIRST``
   :param str campaign_id: The ID of the new campaign.

.. py:function:: campaign-deleted(campaign_id)

   This signal is emitted when the user deletes a campaign. Subscribers
   to this signal can use it to conduct an action after the campaign is deleted.

   :Emission Stage: ``RUN_LAST``
   :param str campaign_id: The ID of the campaign.

.. py:function:: campaign-set(campaign_id)

   This signal is emitted when the user sets the current campaign. Subscribers
   to this signal can use it to update and refresh information for the current
   campaign.

   :Emission Stage: ``RUN_FIRST``
   :param str campaign_id: The ID of the campaign.

.. py:function:: config-load(load_defaults)

   This signal is emitted when the client configuration is loaded from disk. This
   loads all of the clients settings used within the GUI.
   Signal emission stage set to run last.

   :Emission Stage: ``RUN_FIRST``
   :param bool load_defaults: Load defaults true or false.

.. py:function:: config-save()

   This signal is emitted when the client configuration is written to disk. This
   saves all of the settings used within the GUI so they can be restored at a
   later point in time.

   :Emission Stage: ``RUN_LAST``

.. py:function:: credential-delete(row_ids)

   This signal is emitted when the user deletes a credential entry. Subscribers
   to this signal can use it to conduct an action an entry is deleted.

   :Emission Stage: ``RUN_LAST``
   :param list row_ids: The row IDs that are to be deleted.

.. py:function:: exit()

   This signal is emitted when the client is exiting. Subscribers can use it as
   a chance to clean up and save any remaining data. It is emitted before the
   client is disconnected from the server. At this point the exit operation can
   not be cancelled.

   :Emission Stage: ``RUN_LAST``

.. py:function:: exit-confirm()

   This signal is emitted when the client has requested that the application
   exit. Subscribers to this signal can use it as a chance to display a warning
   dialog and cancel the operation.

   :Emission Stage: ``RUN_LAST``

.. py:function:: message-delete(row_ids)

   This signal is emitted when the user deletes a message entry. Subscribers
   to this signal can use it to conduct an action an entry is deleted.

   :Emission Stage: ``RUN_LAST``
   :param list row_ids: The row IDs that are to be deleted.

.. py:function:: message-sent(target_uid, target_email)

   This signal is emitted when the user sends a message. Subscribers
   to this signal can use it to conduct an action after the message is sent,
   and the information saved to the database.

   :Emission Stage: ``RUN_FIRST``
   :param str target_uid: Message uid that was sent.
   :param str target_email: Email address associated with the sent message.

.. py:function:: rpc-cache-clear()

   This signal is emitted to clear the RPC objects cached information.
   Subsequent invocations of RPC cache enabled methods will return fresh
   information from the server.

   :Emission Stage: ``RUN_FIRST``

.. py:function:: server-connected()

   This signal is emitted when the client has connected to the King Phisher
   server. The default handler sets the initial campaign optionally prompting
   the user to select one if one has not already been selected.

   :Emission Stage: ``RUN_LAST``

.. py:function:: server-disconnected()

   This signal is emitted when the client has disconnected from the King Phisher
   server.

   :Emission Stage: ``RUN_FIRST``

.. py:function:: sftp-client-start()

   This signal is emitted when the client starts sftp client from within
   King Phisher. Subscribers can conduct an action prior to the default option
   being ran from the client configuration.
   Signal emission stage set to run last.

   :Emission Stage: ``RUN_LAST``

.. py:function:: visit-delete(row_ids)

   This signal is emitted when the user deletes a visit entry. Subscribers
   to this signal can use it to conduct an action an entry is deleted.

   :Emission Stage: ``RUN_LAST``
   :param list row_ids: The row IDs that are to be deleted.
