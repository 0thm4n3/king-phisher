.. _rpc-api-label:

RPC API
=======

.. py:function:: client/initialize()

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_client_initialize`

.. py:function:: ping()

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_ping`

.. py:function:: shutdown()

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_shutdown`

.. py:function:: version()

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_version`

.. _rpc-api-campaign-api-label:

Campaign API
------------

.. py:function:: campaign/alerts/is_subscribed(campaign_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_alerts_is_subscribed`

.. py:function:: campaign/alerts/subscribe(campaign_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_alerts_subscribe`

.. py:function:: campaign/alerts/unsubscribe(campaign_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_alerts_unsubscribe`

.. py:function:: campaign/delete(campaign_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_delete`

.. py:function:: campaign/landing_page/new(campaign_id, hostname, page)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_landing_page_new`

.. py:function:: campaign/message/new(campaign_id, email_id, email_target, company_name, first_name, last_name)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_message_new`

.. py:function:: campaign/new(name)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_campaign_new`

Campaign Table API
^^^^^^^^^^^^^^^^^^

.. py:function:: campaign/< table_name >/count(campaign_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_count_rows`

.. py:function:: campaign/< table_name >/view(campaign_id, page=0)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_get_rows`

.. _rpc-api-configuration-api-label:

Configuration API
-----------------

.. py:function:: config/get(option_name)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_config_get`

.. py:function:: config/set(options)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_config_set`

.. _rpc-api-message-api-label:

Message API
-----------

.. py:function:: message/credentials/count(message_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_count_rows`

.. py:function:: message/credentials/view(message_id, page=0)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_get_rows`

.. py:function:: message/visits/count(message_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_count_rows`

.. py:function:: message/visits/view(message_id, page=0)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_get_rows`

.. _rpc-api-table-api-label:

Table API
---------

.. py:function:: < table_name >/count()

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_count_rows`

.. py:function:: < table_name >/delete(row_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_delete_row_by_id`

.. py:function:: < table_name >/get(row_id)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_get_row_by_id`

.. py:function:: < table_name >/insert(keys, values)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_insert_row`

.. py:function:: < table_name >/set(row_id, keys, values)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_set_row_value`

.. py:function:: < table_name >/view(page=0)

   :Handler: :py:func:`~king_phisher.server.server_rpc.KingPhisherRequestHandlerRPC.rpc_database_get_rows`
