"""SQL templates for the Oracle adapter.

One template per spatial predicate. The adapter formats placeholders
(`{cols}`, `{tab}`, `{geom_col}`, `{def_query}`, `{distance}`) and
binds AOI geometry via `:wkb_aoi`, `:srid`, optional `:srid_t` (when
applying a coordinate transform), and `:k` (for nearest).

SDO syntax stays in this module by design; the Overlay Engine never
sees SQL; it just calls `adapter.read(predicate=..., ...)`.
"""

# Metadata queries
GEOM_COL = """
    SELECT column_name AS GEOM_NAME
    FROM ALL_SDO_GEOM_METADATA
    WHERE owner = :owner
      AND table_name = :tab_name
"""

SRID = """
    SELECT s.{geom_col}.sdo_srid AS SP_REF
    FROM {tab} s
    WHERE rownum = 1
"""

ALL_TAB_COLUMNS = """
    SELECT column_name
    FROM all_tab_columns
    WHERE owner = :owner
      AND table_name = :tab_name
"""

# Geometry type of the first row, read from SDO_GTYPE - no full scan.
SDO_GTYPE = """
    SELECT s.{geom_col}.sdo_gtype AS GTYPE
    FROM {tab} s
    WHERE rownum = 1
"""

# Optimizer's estimated row count - a fast lookup, no COUNT(*) scan.
# Null for views and for tables whose stats have never been gathered.
NUM_ROWS = """
    SELECT num_rows AS NUM_ROWS
    FROM all_tables
    WHERE owner = :owner
      AND table_name = :tab_name
"""


# Predicate templates. All emit the same final columns:
#   <user-selected cols>, SHAPE.

OVERLAY_INTERSECTS = """
    SELECT {cols},
           SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE
    FROM {tab}
    WHERE SDO_FILTER({geom_col},
                     SDO_GEOMETRY(:wkb_aoi, :srid),
                     'querytype=WINDOW') = 'TRUE'
      AND SDO_RELATE({geom_col},
                     SDO_GEOMETRY(:wkb_aoi, :srid),
                     'mask=ANYINTERACT') = 'TRUE'
        {def_query}
"""

OVERLAY_WITHIN_DISTANCE = """
    SELECT {cols},
           SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE
    FROM {tab}
    WHERE SDO_WITHIN_DISTANCE({geom_col},
                              SDO_GEOMETRY(:wkb_aoi, :srid),
                              'distance={distance}') = 'TRUE'
        {def_query}
"""

OVERLAY_TOUCHES = """
    SELECT {cols},
           SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE
    FROM {tab}
    WHERE SDO_RELATE({geom_col},
                     SDO_GEOMETRY(:wkb_aoi, :srid),
                     'mask=TOUCH') = 'TRUE'
        {def_query}
"""

OVERLAY_NEAREST = """
    SELECT * FROM (
        SELECT {cols},
               SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE
        FROM {tab}
        WHERE SDO_NN({geom_col},
                     SDO_GEOMETRY(:wkb_aoi, :srid),
                     'sdo_num_res=' || :k, 1) = 'TRUE'
            {def_query}
        ORDER BY SDO_NN_DISTANCE(1)
    ) WHERE ROWNUM <= :k
"""


PREDICATE_TEMPLATES = {
    "intersects": OVERLAY_INTERSECTS,
    "within_distance": OVERLAY_WITHIN_DISTANCE,
    "touches": OVERLAY_TOUCHES,
    "nearest": OVERLAY_NEAREST,
}
