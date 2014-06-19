GObject Signals
===============

.. _gobject-signals-kingphisher-client-label:

KingPhisherClient Signals
-------------------------

.. py:function:: campaign_set(campaign_id)

   This signal is emitted when the user sets the current campaign. Subscribers
   to this signal can use it to update and refresh information for the current
   campaign.

   :object: :py:class:`~king_phisher.client.client.KingPhisherClient`
   :param str campaign_id: The ID of the new campaign.
