"""
(From Moez)
Same idea for overlaps: polygons → summed overlap _area_ 
(drops the non-overlapping one); it asks for an `intersects` filter; 
points → keeps only those _inside_ the AOI (count); 
lines → summed overlap _length_; nothing-overlaps → empty result.
"""