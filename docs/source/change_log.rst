Change Log
==========

This document contains notes on the major changes for each version of King
Phisher.

Version 0.2.x
-------------

Version 0.2.1
^^^^^^^^^^^^^

* Added syntax highlighting to the message edit tab
* Support for pulling the client IP from a cookie set by an upstream proxy

Version 0.2.0
^^^^^^^^^^^^^

* Added additional graphs including maps when basemap is available
* Added geolocation support
* Made dashboard layout configurable
* Support for cloning web pages
* Support for installing on Fedora
* Support for running the server with Docker

Version 0.1.x
-------------

Version 0.1.7
^^^^^^^^^^^^^

* Added make_csrf_page function
* Added server support for SSL
* Support verifying the server configuration file
* Added a desktop file and icon for the client GUI
* Added support for operating on multiple rows in the client's campaign tables
* Support starting an external SFTP application from the client
* Tweaked miscellaneous features to scale for larger campaigns (35k+ messages)
* Updated AdvancedHTTPServer to version 0.4.2 which supports Python 3
* Added integration for checking Sender Policy Framework (SPF) records

Version 0.1.6
^^^^^^^^^^^^^

* Migrated to SQLAlchemy backend (SQLite will no longer be supported for database upgrades)
* Added additional documentation to the wiki
* Enhanced error handling and UI documentation for a better user experience
* Support for quickly adding common dates and times in the message editor

Version 0.1.5
^^^^^^^^^^^^^

* Added support for inline images in emails
* Import and export support for message configurations
* Highlight the current campaign in the selection dialog

Version 0.1.4
^^^^^^^^^^^^^

* Full API documentation
* Install script for Kali & Ubuntu
* Lots of bug fixes

Version 0.1.3
^^^^^^^^^^^^^

* Jinja2 templates for both the client and server
* API version checking to warn when the client and server versions are incompatible
