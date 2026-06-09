Public Transport
================

Public transport data is a key element of transport planning in general [1]_. AequilibraE can
populate its public transport database from GTFS feeds and from supported VISUM SQLite public
transport tables. GTFS is a standardized data format widely used in public transport planning and
operation, and was first proposed during the 2000s', for public transit agencies to describe
details from their services, such as schedules, stops, fares, etc [2]_. Currently,
there are two types of GTFS data:

* GTFS schedule, which contains information on routes, schedules, fares, and other details;
* GTFS realtime, which contains real-time vehicle position, trip updates, and service alerts.

The GTFS protocol is being constantly updated and so are AequilibraE's capabilities of handling
these changes. We strongly encourage you to take a look at the documentation provided
by `Mobility Data <https://gtfs.org/documentation/schedule/reference/>`_.

VISUM SQLite public-transport import is intended for projects whose private network has already
been imported from the same VISUM SQLite source with preserved VISUM node, link, and zone
identifiers. It reads supported operators, stop points, line routes, time profiles, vehicle
journeys, and schedules into the same service tables used by GTFS imports, then relies on the
existing transit graph and preload workflows.

A typical VISUM SQLite workflow imports the private network first, then imports public transport
service data:

.. code-block:: python

   project.network.create_from_visum_sqlite(path, mode_mapping={"CAR": "c", "BUS": "t"})
   report = project.transit.import_from_visum_sqlite(path)

The transit import validates that the project contains compatible ``visum_node_no``,
``visum_link_no``, and ``visum_zone_no`` source-reference fields before writing service data.
Existing transit service rows are protected by default; pass ``overwrite=True`` when replacing
previously imported public transport data. Saved transit graph configurations are removed when
service data is overwritten, because the graph must be rebuilt from the replacement routes and
schedules. Detailed fares, transfer-walk-time rules, vehicle blocking and coupling, depot data,
and detailed calendar semantics are reported as deferred VISUM public-transport scope.

In this section we also present the transit assignment models, which are mathematical tools that
predict how passengers behave and travel in a transit network, given some assumptions and inputs.

Transit assignment models aim to answer questions such as:

* How do transit passengers choose their routes in a complex network of lines and services?
* How can we estimate the distribution of passenger flows and the performance of transit systems?

.. seealso::
   
   * :ref:`public_transport_database`
      Database structure
   * :ref:`example_visum_sqlite_transit`
      VISUM SQLite public transport example

.. toctree::
   :caption: Public Transport
   :maxdepth: 1
   
   public_transport/transit_graph
   public_transport/hyperpath_routing
   public_transport/transit_skimming
   _auto_examples/public_transport/index

References
----------

.. [1] Pereira, R.H.M. and Herszenhut, D. (2023) Introduction to urban accessibility:
       a practical guide with R. Rio de Janeiro, IPEA. Available at:
       https://repositorio.ipea.gov.br/bitstream/11058/12689/52/Introduction_urban_accessibility_Book.pdf

.. [2] Mobility Data (2024) GTFS: Making Public Transit Data Universally Accessible. 
       Available at: https://gtfs.org/getting-started/what-is-GTFS/
