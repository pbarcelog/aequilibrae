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

Regional GTFS feeds can cover a much larger service area than the project network. Before using
network-based map matching, coverage diagnostics can evaluate route patterns built from ordered
``stop_times.txt`` stop sequences against the project network. The diagnostics classify stops as
matched to the route-type modal graph, near the model but not near the required modal links,
outside the model range, ambiguous, unmatched, or unsupported by the route-type mapping.
Patterns are accepted only when all retained stops are matched and connected through the modal
network. Missing coverage may be trimmed only at the beginning or end of a pattern; internal
coverage gaps and internal modal discontinuities are rejected rather than simplified into a
substitute route.

When coverage-approved patterns are synthesized for assignment-ready import, AequilibraE records
geometry sources and quality diagnostics rather than treating inferred paths as authoritative
truth. The supported synthesis modes are:

* ``gtfs-shape``: GTFS ``shapes.txt`` guides map matching when trips reference a loaded shape and
  the shape can be matched to a connected route-type-compatible link sequence.
* ``inferred-preferred``: stop-to-stop network inference prefers higher-priority or main-street
  links when they stay within the configured detour ratio.
* ``inferred-fallback``: stop-to-stop inference uses the shortest compatible modal path when
  preferred routing is unavailable, unsupported by stop context, or too circuitous.
* ``rejected``: a pattern or segment cannot be matched, connected, or kept within configured
  thresholds.

No-shape feeds are common in practice. The inference workflow is intentionally qualitative: it
builds a first assignment-usable draft from ordered stops and the project network, exposes
fallback and rejection reasons, and does not guarantee real-world vehicle paths. When a feed
references GTFS shapes but shape-guided matching fails, synthesis falls back to stop-to-stop
inference and records ``shape-guided-unavailable`` in the diagnostics. A real local feed with
``shapes.txt`` remains an important validation target for tuning the shape-guided branch.

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
