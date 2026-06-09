.. _public_transport_database:

Public Transport Database
=========================

AequilibraE's transit module has been updated in version 0.9.0 and more details on 
the **public_transport.sqlite** are discussed on a nearly *per-table* basis below. We
recommend understanding the role of each table before setting an AequilibraE model 
you intend to use.

The public transport database is created on the run when the ``Transit`` module is executed
for the first time and it can take a little while.

Transit service tables can be populated by GTFS import workflows or by supported VISUM SQLite
public-transport imports. VISUM SQLite imports use the same service-table contracts for
``agencies``, ``stops``, ``routes``, ``route_links``, ``pattern_mapping``, ``trips``, and
``trips_schedule`` as the graph builder expects from GTFS-derived data. Importer-specific source
coverage and unsupported VISUM features are reported through the import report rather than by
adding VISUM-only columns to the transit schema.

The generated transit graph tables, including transit ``nodes`` and ``links``, are still created by
``Transit.create_graph()`` for a selected period and graph configuration. VISUM SQLite transit
imports do not write those generated graph tables directly.

.. seealso::

    * :func:`aequilibrae.transit.transit.Transit`
        Class documentation
    * :func:`aequilibrae.transit.transit_graph_builder.TransitGraphBuilder`
        Class documentation

In the following sections, we'll dive deep into the tables existing in the public transport database.
Please notice that some tables are homonyms to the ones existing in the **project_database.sqlite**,
but its contents are related to the public transport graph building and assignment processes. 
