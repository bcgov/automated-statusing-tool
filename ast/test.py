from .core.data_adapters.kml.adapter import KMLAdapter
import geopandas as gpd

def test():
    
    gdf = KMLAdapter().read(path="ast_app/Test_Shape_A/Test_Shape_A.kmz", target_crs="EPSG:3005")

    print(type(gdf))
    print(gdf.shape)
    print(gdf.crs)
    print(gdf.head())

    def test_kml_adapter_reads_file():
        adapter = KMLAdapter()
        gdf = adapter.read(path="ast_app/Test_Shape_A/Test_Shape_A.kmz")
        assert gdf is not None
        assert gdf.crs is not None
        assert len(gdf) > 0

if __name__ == "__main__":
    test()