"""
(From Moez)
Feeds the operator a pretend data source with points at known distances 
(3 m, 10 m, 2 km from a 1 km AOI box) 
and checks: `within_distance(12)` keeps the 3 m + 10 m points (closest first) 
and reports 3 m; 
it asks the source for a `within_distance` filter; `nearest(k=2)` 
returns the 2 closest; nothing-found gives an empty result;
a lat/long AOI is rejected (distances need metres).

Proximity operator test 


Purpose:
- Feed the operator a pretend data source with known points at known distance 
    - 3m, 10m, 2km (from a 1km AOI box)
- Check that `within_distance(12)` keeps the 3 m + 10 m points (closest first)
- Ask the source to return the following: 
    - `within_distance(12)` returns the 3 m + 10 m points (closest first) and reports 3 m
    - `nearest(k=2)` returns the 2 closest points
    - Nothing-found gives an empty result
    - A lat/long AOI is rejected (distances need metres) ???


HOW TO EXTEND:
-------------
1. 

Example:
def test_file_adapter_read_shp()
def 




"""

