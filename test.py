import geopandas as gpd

gdf = gpd.read_file("ast_app/Test_Shape_A/Test_Shape_A.kmz")

print(gdf)