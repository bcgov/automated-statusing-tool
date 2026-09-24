import React, { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import XYZ from "ol/source/XYZ";
import VectorSource from "ol/source/Vector";
import { OSM } from "ol/source";
import { GeoJSON } from "ol/format";
import { fromLonLat } from "ol/proj";
import { Fill, Stroke, Style } from "ol/style";
import ScaleLine from "ol/control/ScaleLine";

import "ol/ol.css";

type BasemapId = "street" | "satellite";

interface TantalisPreviewRequest {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

interface OLMapProps {
  center?: [number, number];
  zoom?: number;
  onPolygonClick?: (dispositionId: string) => void;
  tantalisPreview?: TantalisPreviewRequest | null;
}

const DEFAULT_PREVIEW_HUE = 120;
const DEFAULT_PREVIEW_OPACITY = 70;

// updated week of sept 21: custom SVG icons replace the blurry emoji buttons so the basemap and symbology tools read clearly as map and paint symbols.
const PaperMapIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M4 6.5V17.5L8.5 15.5L15.5 18.5L20 16.5V5.5L15.5 7.5L8.5 4.5L4 6.5Z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path d="M8.5 4.5V15.5M15.5 7.5V18.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

const PaintbrushIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M4 15.5L12.5 7L16.5 11L8 19.5H4V15.5Z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path d="M13.5 6.5L17.5 2.5L20.5 5.5L16.5 9.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4.5 19.5H7.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

const getPreviewAppearance = (hue: number, transparency: number) => {
  // updated fix: 0% transparency means the parcel is fully opaque, and 100% transparency means it is effectively invisible.
  const alpha = Math.min(1, Math.max(0, 1 - transparency / 100));
  return {
    fill: `hsla(${hue}, 70%, 50%, ${alpha})`,
    stroke: `hsla(${hue}, 65%, 30%, 1)`,
    width: 2.5,
  };
};

interface DisclaimerLink {
  label: string;
  value: string;
}

const GOV_BC_BASE_URL = "https://" + "www2.gov.bc.ca/gov/content?id=";

const DISCLAIMER_LINKS: DisclaimerLink[] = [
  {
    label: "Disclaimer",
    value: `${GOV_BC_BASE_URL}79F93E018712422FBC8E674A67A70535`,
  },
  {
    label: "Privacy",
    value: `${GOV_BC_BASE_URL}9E890E16955E4FF4BF3B0E07B4722932`,
  },
  {
    label: "Accessibility",
    value: `${GOV_BC_BASE_URL}E08E79740F9C41B9B0C484685CC5E412`,
  },
  {
    label: "Contact us",
    value: `${GOV_BC_BASE_URL}6A77C17D0CCB48F897F8598CCC019111`,
  },
];

const STREET_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Street_Map/MapServer/tile/{z}/{y}/{x}";

const SATELLITE_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Imagery/MapServer/tile/{z}/{y}/{x}";

const DEFAULT_CENTER: [number, number] = [-123.3656, 48.4284];
const DEFAULT_ZOOM = 8;

// The map component owns the OpenLayers instance and the basemap/view behavior used by the page.
const OLMap: React.FC<OLMapProps> = ({
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  onPolygonClick,
  tantalisPreview,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);

  const [selectedBasemap, setSelectedBasemap] = useState<BasemapId>("satellite");
  const [showBasemapPanel, setShowBasemapPanel] = useState(false);
  const [showShapeSymbologyPanel, setShowShapeSymbologyPanel] = useState(false);
  const [isDisclaimerExpanded, setIsDisclaimerExpanded] = useState(false);
  const [selectedDisclaimerItem, setSelectedDisclaimerItem] = useState("");
  // updated week of sept 21: preview styling now lives in state so the user can drag the colour and transparency while reviewing the parcel.
  const [previewHue, setPreviewHue] = useState<number>(DEFAULT_PREVIEW_HUE);
  const [previewOpacity, setPreviewOpacity] = useState<number>(DEFAULT_PREVIEW_OPACITY);
  const previewLayerRef = useRef<VectorLayer | null>(null);

  // Initialize the map one time and set the starting view, leaving the rest of the behavior to later effects.
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    const baseLayer = new TileLayer({
      source: new XYZ({
        url: STREET_URL,
        crossOrigin: "anonymous",
      }),
    });

    const map = new Map({
      target: mapContainerRef.current,
      layers: [baseLayer],
      view: new View({
        center: fromLonLat(center),
        zoom,
      }),
      controls: [],
    });

    map.addControl(
      new ScaleLine({
        className: "burn-severity-scale",
        units: "metric",
        minWidth: 140,
      })
    );

    mapRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  // Keep the viewport aligned with the page's desired center/zoom without re-creating the map instance.
  useEffect(() => {
    const map = mapRef.current;

    if (!map) {
      return;
    }

    map.getView().animate({
      center: fromLonLat(center),
      zoom,
      duration: 400,
    });
  }, [center, zoom]);

  // Toggle between the street and satellite tile source when the user changes the basemap setting.
  useEffect(() => {
    const map = mapRef.current;

    if (!map) {
      return;
    }

    const baseLayer = map.getLayers().item(0) as TileLayer<OSM | XYZ> | undefined;

    if (!baseLayer) {
      return;
    }

    if (selectedBasemap === "street") {
      baseLayer.setSource(
        new XYZ({
          url: STREET_URL,
          crossOrigin: "anonymous",
          attributions: "Tiles © Esri",
        })
      );
      return;
    }

    baseLayer.setSource(
      new XYZ({
        url: SATELLITE_URL,
        crossOrigin: "anonymous",
        attributions: "Tiles © Esri",
      })
    );
  }, [selectedBasemap]);

  //container resize watcher - keeps the map viewport synced when the layout changes
  useEffect(() => {
    const mapContainer = mapContainerRef.current;

    if (!mapContainer) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      mapRef.current?.updateSize();
    });

    resizeObserver.observe(mapContainer);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  //reflow after disclaimer panel opens/closes so the map redraws correctly
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      mapRef.current?.updateSize();
    }, 50);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [isDisclaimerExpanded]);

  //zoom controls - adjust the map scale smoothly without re-creating the map
  const zoomIn = () => {
    const view = mapRef.current?.getView();

    if (!view) {
      return;
    }

    view.animate({
      zoom: (view.getZoom() ?? zoom) + 1,
      duration: 200,
    });
  };

  const zoomOut = () => {
    const view = mapRef.current?.getView();

    if (!view) {
      return;
    }

    view.animate({
      zoom: (view.getZoom() ?? zoom) - 1,
      duration: 200,
    });
  };

  //footer disclaimer menu - opens the selected policy link in a new tab
  const handleDisclaimerSelect = (
    event: React.ChangeEvent<HTMLSelectElement>
  ) => {
    const nextValue = event.target.value;
    setSelectedDisclaimerItem(nextValue);

    if (!nextValue) {
      return;
    }

    window.open(nextValue, "_blank", "noopener,noreferrer");
    setSelectedDisclaimerItem("");
  };

  // When the form sends TANTALIS identifiers, query the public WFS layer and draw the matching parcel on the map.
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !tantalisPreview) {
      return;
    }

    const url = new URL("https://openmaps.gov.bc.ca/geo/pub/ows");
    url.searchParams.set("service", "WFS");
    url.searchParams.set("version", "2.0.0");
    url.searchParams.set("request", "GetFeature");
    url.searchParams.set("typeNames", "pub:WHSE_TANTALIS.TA_CROWN_TENURES_SVW");
    url.searchParams.set("outputFormat", "application/json");
    url.searchParams.set("srsName", "EPSG:4326");

    const filter = [
      `CROWN_LANDS_FILE='${tantalisPreview.fileNumber}'`,
      `DISPOSITION_TRANSACTION_SID=${tantalisPreview.dispositionId}`,
      `INTRID_SID=${tantalisPreview.parcelId}`,
    ].join(" AND ");

    url.searchParams.set("CQL_FILTER", filter);

    const previewAppearance = getPreviewAppearance(previewHue, previewOpacity);
    const previewLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        fill: new Fill({ color: previewAppearance.fill }),
        stroke: new Stroke({ color: previewAppearance.stroke, width: previewAppearance.width }),
      }),
      zIndex: 120,
    });

    if (previewLayerRef.current) {
      map.removeLayer(previewLayerRef.current);
    }

    map.addLayer(previewLayer);
    previewLayerRef.current = previewLayer;

    fetch(url.toString())
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Tantalus WFS query failed: ${response.status}`);
        }

        return response.json();
      })
      .then((geoJson) => {
        const features = new GeoJSON().readFeatures(geoJson, {
          featureProjection: "EPSG:3857",
          dataProjection: "EPSG:4326",
        });

        if (!features.length) {
          throw new Error("No Tantalus parcel matched the query.");
        }

        const source = previewLayer.getSource();
        if (!source) {
          return;
        }

        source.clear();
        source.addFeatures(features);

        const extent = source.getExtent();
        map.getView().fit(extent, {
          padding: [30, 30, 30, 30],
          maxZoom: 16,
          duration: 600,
        });
      })
      .catch((error) => {
        console.error("Tantalus preview failed", error);
        map.removeLayer(previewLayer);
        previewLayerRef.current = null;
      });

    return () => {
      if (previewLayerRef.current) {
        map.removeLayer(previewLayerRef.current);
        previewLayerRef.current = null;
      }
    };
  }, [tantalisPreview, previewHue, previewOpacity]);

  // updated week of sept 21: the parcel preview layer now supports a live colour and transparency control for map review.
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !previewLayerRef.current) {
      return;
    }

    const layerAppearance = getPreviewAppearance(previewHue, previewOpacity);
    const layerStyle = new Style({
      fill: new Fill({ color: layerAppearance.fill }),
      stroke: new Stroke({ color: layerAppearance.stroke, width: layerAppearance.width }),
    });

    previewLayerRef.current.setStyle(layerStyle);
  }, [previewHue, previewOpacity]);

  // Listen for user clicks on map features and pass the selected disposition ID back up to the page.
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !onPolygonClick) {
      return;
    }

    const handleMapClick = (event: any) => {
      const clickedFeature = map.forEachFeatureAtPixel(event.pixel, (feature) => feature);

      if (!clickedFeature || !clickedFeature.get("DISPOSITION_TRANSACTION_SID")) {
        return;
      }

      const dispositionId = String(clickedFeature.get("DISPOSITION_TRANSACTION_SID"));
      onPolygonClick(dispositionId);
    };

    map.on("click", handleMapClick);

    return () => {
      map.un("click", handleMapClick);
    };
  }, [onPolygonClick]);

  return (
    <div className="map-shell">
      <div className="map-frame">
        {/* map container - OpenLayers mounts here and fills the available viewport */}
        <div
          ref={mapContainerRef}
          className="map-container"
          aria-label="Interactive map"
        />

        <div className="map-controls map-controls--right">
          {/* updated week of sept 21: map toolbar stays above the live symbology control so the preview can be adjusted in place. */}
          <div className="map-zoom-panel">
            <button type="button" onClick={zoomIn} aria-label="Zoom in" title="Zoom in">
              +
            </button>

            <button type="button" onClick={zoomOut} aria-label="Zoom out" title="Zoom out">
              −
            </button>
          </div>

          <div className="map-basemap-wrap">
            {/* updated week of sept 21: compact basemap toggle keeps the map toolbar tight, but expands on hover to reveal the full label while still opening the basemap picker on click. */}
            <button
              type="button"
              className="map-tool-toggle map-basemap-toggle"
              aria-expanded={showBasemapPanel}
              aria-controls="basemap-panel"
              onClick={() => setShowBasemapPanel((currentValue) => !currentValue)}
            >
              <span className="map-tool-toggle__icon map-tool-toggle__icon--map" aria-hidden="true">
                <PaperMapIcon />
              </span>
              <span className="map-tool-toggle__label">Basemap</span>
            </button>

            {showBasemapPanel && (
              <div
                id="basemap-panel"
                className="basemap-panel"
                role="group"
                aria-label="Basemap options"
              >
                <div className="basemap-panel__header">
                  <span>Select map</span>

                  <button
                    type="button"
                    aria-label="Close basemap options"
                    title="Close basemap options"
                    onClick={() => setShowBasemapPanel(false)}
                  >
                    −
                  </button>
                </div>

                <label className="basemap-option">
                  <input
                    type="radio"
                    name="basemap"
                    value="street"
                    checked={selectedBasemap === "street"}
                    onChange={() => setSelectedBasemap("street")}
                  />

                  <span>Street</span>
                </label>

                <label className="basemap-option">
                  <input
                    type="radio"
                    name="basemap"
                    value="satellite"
                    checked={selectedBasemap === "satellite"}
                    onChange={() => setSelectedBasemap("satellite")}
                  />

                  <span>Satellite</span>
                </label>
              </div>
            )}
          </div>

          {tantalisPreview && (
            <div className="map-shape-symbology-wrap">
              {/* updated week of sept 21: this optional tool mirrors the basemap control behavior so the toolbar remains compact until the user opens the live parcel styling panel. */}
              <button
                type="button"
                className="map-tool-toggle map-shape-symbology-toggle"
                aria-expanded={showShapeSymbologyPanel}
                aria-controls="shape-symbology-panel"
                onClick={() => setShowShapeSymbologyPanel((currentValue) => !currentValue)}
              >
                <span className="map-tool-toggle__icon map-tool-toggle__icon--paint" aria-hidden="true">
                  <PaintbrushIcon />
                </span>
                <span className="map-tool-toggle__label">Shape symbology</span>
              </button>

              {showShapeSymbologyPanel && (
                <div
                  id="shape-symbology-panel"
                  className="map-preview-style-panel"
                  role="group"
                  aria-label="Shape symbology"
                >
                  <label className="map-preview-control">
                    <span>Colour</span>
                    <input
                      type="range"
                      min="0"
                      max="360"
                      value={previewHue}
                      onChange={(event) => setPreviewHue(Number(event.target.value))}
                      className="map-preview-hue-slider"
                    />
                  </label>

                  <label className="map-preview-control">
                    <span>Transparency: {previewOpacity}%</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={previewOpacity}
                      onChange={(event) => setPreviewOpacity(Number(event.target.value))}
                      className="map-preview-transparency-slider"
                    />
                  </label>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

    </div>
  );
};

export default OLMap;
