// React tools:
// useEffect = run code after the page draws (for example, set up the map).
// useRef = keep a value between redraws without causing a redraw.
// useState = store a value that redraws the page when it changes.
import { useEffect, useRef, useState } from "react";
// FC = "function component". Used here only as a type, so it adds nothing to the final app.
import type { FC } from "react";

// OpenLayers pieces used to build the map.
import Map from "ol/Map";
import View from "ol/View"; // Controls where the map looks (center and zoom)
import TileLayer from "ol/layer/Tile"; // Layer for basemap image tiles
import VectorLayer from "ol/layer/Vector"; // Layer for shapes (Tantalis preview)
import XYZ from "ol/source/XYZ"; // Loads tiles from a URL pattern like {z}/{y}/{x}
import VectorSource from "ol/source/Vector"; // Holds the shapes shown in a vector layer
import { GeoJSON } from "ol/format"; // Reads GeoJSON data into shapes OpenLayers can draw
import { fromLonLat } from "ol/proj"; // Converts longitude/latitude into map coordinates
import { Fill, Stroke, Style } from "ol/style"; // Fill colour, outline and full shape style
import ScaleLine from "ol/control/ScaleLine"; // The scale bar
import { unByKey } from "ol/Observable"; // Removes an event listener that was added with map.on()
// Feature = one shape on the map. Used only as a type.
import type Feature from "ol/Feature";

// Default OpenLayers styling.
import "ol/ol.css";

// The only two basemap choices.
type BasemapId = "street" | "satellite";

// The three Tantalis identifiers. All values are kept as strings in the app
interface TantalisIdentifiers {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

// Everything LandingPage can pass into this map. The ? means the value is optional.
interface OLMapProps {
  // Starting point as [longitude, latitude].
  center?: [number, number];
  // Starting zoom level. Bigger number = closer in.
  zoom?: number;
  // Runs when a shape is clicked. Sends its three identifiers back up to LandingPage.
  onPolygonClick?: (selection: TantalisIdentifiers) => void;
  // Identifiers sent from the form. When this changes, the map looks up and shows the shape.
  tantalisPreview?: TantalisIdentifiers | null;
}

// Starting colour of the preview shape. 120 on the colour wheel = green.
const DEFAULT_PREVIEW_HUE = 120;
const DEFAULT_PREVIEW_OPACITY = 70;
// Starting map location in the middle of BC
const DEFAULT_CENTER: [number, number] = [-126.5, 54.6];
// Starting zoom level. 5 shows the whole province.
const DEFAULT_ZOOM = 5;

// Tile addresses for the two basemaps. {z} = zoom, {y} = row, {x} = column.
const STREET_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

// BC Open Maps web service (WFS) used to look up Tantalis shapes.
const TANTALIS_WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/ows";
// The Tantalis Crown tenures layer to search.
const TANTALIS_LAYER = "pub:WHSE_TANTALIS.TA_CROWN_TENURES_SVW";

// Credit shown for the Esri basemap tiles.
const ESRI_ATTRIBUTION = "Tiles © Esri";

// Builds a basemap tile source from a tile URL.
// crossOrigin lets the browser use tiles from another website safely.
const createBasemapSource = (url: string): XYZ =>
  new XYZ({ url, crossOrigin: "anonymous", attributions: ESRI_ATTRIBUTION });

// Icon for the Basemap button (a folded paper map).
// In each d="..." drawing path: M = move to, V = vertical line, L = line to, Z = close the shape.
const PaperMapIcon: FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {/* Outline of the folded map */}
    <path
      d="M4 6.5V17.5L8.5 15.5L15.5 18.5L20 16.5V5.5L15.5 7.5L8.5 4.5L4 6.5Z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    {/* The two fold lines */}
    <path d="M8.5 4.5V15.5M15.5 7.5V18.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// Icon for the Shape symbology button (a paintbrush).
const PaintbrushIcon: FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {/* Brush head */}
    <path
      d="M4 15.5L12.5 7L16.5 11L8 19.5H4V15.5Z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    {/* Brush handle */}
    <path
      d="M13.5 6.5L17.5 2.5L20.5 5.5L16.5 9.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Paint stroke under the brush */}
    <path d="M4.5 19.5H7.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// Builds the style for the preview shape from the two sliders.
// hue = colour wheel position (0-360). transparency = 0% solid to 100% invisible.
const buildPreviewStyle = (hue: number, transparency: number): Style => {
  // Turn transparency into alpha (1 = solid, 0 = invisible), kept between 0 and 1.
  const alpha = Math.min(1, Math.max(0, 1 - transparency / 100));

  return new Style({
    // Inside colour. Gets more see-through as transparency goes up.
    fill: new Fill({ color: `hsla(${hue}, 70%, 50%, ${alpha})` }),
    // Outline. A darker version of the same colour, always solid.
    stroke: new Stroke({ color: `hsla(${hue}, 65%, 30%, 1)`, width: 2.5 }),
  });
};

// Returns true when the text contains only the digits 0-9.
const isDigitsOnly = (value: string): boolean => /^\d+$/.test(value);

// Doubles any apostrophes (' becomes '') so text is safe inside a quoted filter value.
const escapeCqlText = (value: string): string => value.replace(/'/g, "''");

// The map component. It creates the OpenLayers map and handles everything the map does.
const OLMap: FC<OLMapProps> = ({
  // If LandingPage doesn't send a center or zoom, use the defaults.
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  onPolygonClick,
  tantalisPreview,
}) => {
  // The <div> the map is drawn inside.
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  // The OpenLayers map, so every part of this file can reach it.
  const mapRef = useRef<Map | null>(null);
  // The layer showing the current TANTALIS preview shape, so the sliders can restyle it.
  const previewLayerRef = useRef<VectorLayer<VectorSource> | null>(null);

  // Which basemap is selected. Starts on satellite.
  const [selectedBasemap, setSelectedBasemap] = useState<BasemapId>("satellite");
  // Whether the basemap picker is open.
  const [showBasemapPanel, setShowBasemapPanel] = useState<boolean>(false);
  // Whether the colour/transparency panel is open.
  const [showShapeSymbologyPanel, setShowShapeSymbologyPanel] = useState<boolean>(false);
  // Current colour slider value.
  const [previewHue, setPreviewHue] = useState<number>(DEFAULT_PREVIEW_HUE);
  // Current transparency slider value.
  const [previewOpacity, setPreviewOpacity] = useState<number>(DEFAULT_PREVIEW_OPACITY);
  // Message shown on the map while loading, or when the lookup fails or finds nothing.
  // An empty string means no message is shown.
  const [previewStatus, setPreviewStatus] = useState<string>("");

  // 1. Create the map one time when the component first appears.
  useEffect(() => {
    // Stop if the <div> isn't ready yet, or the map already exists.
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    // Basemap layer. Starts on satellite to match the selected option.
    const baseLayer = new TileLayer({ source: createBasemapSource(SATELLITE_URL) });

    const map = new Map({
      target: mapContainerRef.current, // Draw the map inside our <div>
      layers: [baseLayer], // Basemap is always the first (bottom) layer
      view: new View({ center: fromLonLat(center), zoom }),
      controls: [], // Hide the default OpenLayers buttons. We use our own.
    });

    // Add the scale bar in metres/kilometres.
    // The class name matches the existing CSS that positions and styles it.
    map.addControl(new ScaleLine({ className: "burn-severity-scale", units: "metric", minWidth: 140 }));

    // Save the map so the rest of the file can use it.
    mapRef.current = map;

    // Clean up when the component is removed from the page.
    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
    // The empty list [] means this runs only once. Later center/zoom changes are handled in step 2.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. Move the map smoothly when the center or zoom props change.
  useEffect(() => {
    mapRef.current?.getView().animate({ center: fromLonLat(center), zoom, duration: 400 });
  }, [center, zoom]);

  // 3. Swap the basemap tiles when the user picks Street or Satellite.
  useEffect(() => {
    // The basemap is always the first layer.
    const baseLayer = mapRef.current?.getLayers().item(0);

    // Stop if the map isn't ready or the first layer isn't a tile layer.
    if (!(baseLayer instanceof TileLayer)) {
      return;
    }

    const url = selectedBasemap === "street" ? STREET_URL : SATELLITE_URL;
    baseLayer.setSource(createBasemapSource(url));
  }, [selectedBasemap]);

  // 4. Resize the map whenever its container changes size (for example, when the layout shifts).
  useEffect(() => {
    const mapContainer = mapContainerRef.current;
    if (!mapContainer) {
      return;
    }

    // ResizeObserver watches the <div> and runs updateSize whenever its size changes.
    const resizeObserver = new ResizeObserver(() => {
      mapRef.current?.updateSize();
    });
    resizeObserver.observe(mapContainer);

    // Stop watching when the component is removed.
    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // 5. Look up and show the Tantalis shape whenever the form sends new identifiers.
  // The sliders are left out of the list at the bottom, so moving them doesn't repeat the lookup.
  useEffect(() => {
    const map = mapRef.current;

    // Stop if the map isn't ready or nothing has been sent yet.
    if (!map || !tantalisPreview) {
      return;
    }

    // Remove extra spaces from the start and end of each value.
    const fileNumber = tantalisPreview.fileNumber.trim();
    const dispositionId = tantalisPreview.dispositionId.trim();
    const parcelId = tantalisPreview.parcelId.trim();

    // The two ID fields are compared as numbers in the filter below,
    // so stop here if they contain anything other than digits.
    if (!isDigitsOnly(dispositionId) || !isDigitsOnly(parcelId)) {
      setPreviewStatus("Disposition ID and Parcel ID must contain numbers only.");
      return;
    }

    // Build the web address for the lookup.
    const url = new URL(TANTALIS_WFS_URL);
    url.searchParams.set("service", "WFS"); // Type of web service
    url.searchParams.set("version", "2.0.0"); // WFS version
    url.searchParams.set("request", "GetFeature"); // Ask for shapes
    url.searchParams.set("typeNames", TANTALIS_LAYER); // Which layer to search
    url.searchParams.set("outputFormat", "application/json"); // Send results back as GeoJSON
    url.searchParams.set("srsName", "EPSG:4326"); // Send coordinates as longitude/latitude

    // The filter: only return the shape where all three identifiers match.
    // The file number is text, so it goes in quotes. The two IDs are numbers, so no quotes.
    url.searchParams.set(
      "CQL_FILTER",
      [
        `CROWN_LANDS_FILE='${escapeCqlText(fileNumber)}'`,
        `DISPOSITION_TRANSACTION_SID=${dispositionId}`,
        `INTRID_SID=${parcelId}`,
      ].join(" AND ")
    );

    // Create an empty layer for the preview shape, using the current slider values.
    const previewSource = new VectorSource();
    const previewLayer = new VectorLayer({
      source: previewSource,
      style: buildPreviewStyle(previewHue, previewOpacity),
      zIndex: 120, // Draw above the basemap
    });

    map.addLayer(previewLayer);
    previewLayerRef.current = previewLayer;
    setPreviewStatus("Loading TANTALIS shape...");

    // Lets us cancel this request if new identifiers arrive before it finishes.
    const controller = new AbortController();

    // Send the request to BC Open Maps.
    fetch(url.toString(), { signal: controller.signal })
      .then((response) => {
        // Stop with an error if the service returned a problem (for example, 404 or 500).
        if (!response.ok) {
          throw new Error(`the map service returned status ${response.status}`);
        }
        // Read the reply as JSON.
        return response.json();
      })
      .then((geoJson: unknown) => {
        // Turn the GeoJSON into shapes, converting from longitude/latitude
        // into the map's own coordinate system (EPSG:3857).
        // "as Feature[]" tells TypeScript these are normal shapes that can be added to the layer.
        // Some OpenLayers versions label the result with a wider type that addFeatures won't accept.
        const features = new GeoJSON().readFeatures(geoJson, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        }) as Feature[];

        // Nothing matched, so tell the user.
        if (features.length === 0) {
          setPreviewStatus("No TANTALIS shape matched all three identifiers. Check the values and try again.");
          return;
        }

        // Draw the shape.
        previewSource.addFeatures(features);

        // Get the box around the shape so the map can zoom to it.
        // getExtent() can return null (no box), so check it before zooming.
        const extent = previewSource.getExtent();
        if (!extent) {
          setPreviewStatus("The TANTALIS shape was found but has no area to zoom to.");
          return;
        }

        // Zoom the map to fit the shape.
        map.getView().fit(extent, {
          padding: [30, 30, 30, 30], // Space around the shape, in pixels
          maxZoom: 16, // Don't zoom in too far on very small shapes
          duration: 600, // Animation length, in milliseconds
        });

        // Success, so clear the loading message.
        setPreviewStatus("");
      })
      .catch((error: unknown) => {
        // A cancelled request is normal when a newer one replaces it, so ignore it.
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        // Anything else is a real problem, so show it on the map.
        const reason = error instanceof Error ? error.message : "unknown error";
        setPreviewStatus(`Could not load the TANTALIS shape: ${reason}.`);
      });

    // Clean up: runs before the next lookup or when the map is removed.
    // Cancels the request and removes this preview shape from the map.
    return () => {
      controller.abort();
      map.removeLayer(previewLayer);
      if (previewLayerRef.current === previewLayer) {
        previewLayerRef.current = null;
      }
    };
    // Only rerun when new identifiers arrive. The slider values are left out on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tantalisPreview]);

  // 6. Restyle the current preview shape when the colour or transparency slider moves.
  useEffect(() => {
    previewLayerRef.current?.setStyle(buildPreviewStyle(previewHue, previewOpacity));
  }, [previewHue, previewOpacity]);

  // 7. When a shape is clicked, send its three identifiers back up to LandingPage.
  useEffect(() => {
    const map = mapRef.current;

    // Stop if the map isn't ready or LandingPage didn't send a click function.
    if (!map || !onPolygonClick) {
      return;
    }

    // Listen for clicks. clickKey is used later to remove this listener.
    const clickKey = map.on("click", (event) => {
      // Find the shape under the mouse, if there is one.
      const clickedFeature = map.forEachFeatureAtPixel(event.pixel, (feature) => feature);
      if (!clickedFeature) {
        return;
      }

      // Read the three identifiers from the shape's attributes.
      // unknown = the value could be any type until we check it.
      const fileNumber: unknown = clickedFeature.get("CROWN_LANDS_FILE");
      const dispositionId: unknown = clickedFeature.get("DISPOSITION_TRANSACTION_SID");
      const parcelId: unknown = clickedFeature.get("INTRID_SID");

      // Stop if any identifier is missing. (== null catches both null and undefined.)
      if (fileNumber == null || dispositionId == null || parcelId == null) {
        return;
      }

      // Send them up as text, so they fit straight into the form fields.
      onPolygonClick({
        fileNumber: String(fileNumber),
        dispositionId: String(dispositionId),
        parcelId: String(parcelId),
      });
    });

    // Stop listening when the component is removed or onPolygonClick changes.
    return () => {
      unByKey(clickKey);
    };
  }, [onPolygonClick]);

  // Zoom in (delta = 1) or out (delta = -1) with a short animation.
  const zoomBy = (delta: number): void => {
    const view = mapRef.current?.getView();
    if (!view) {
      return;
    }
    // Use the current zoom. If it's not available, fall back to the starting zoom.
    view.animate({ zoom: (view.getZoom() ?? zoom) + delta, duration: 200 });
  };

  // What appears on the page.
  return (
    <div className="map-shell">
      <div className="map-frame">
        {/* OpenLayers draws the map inside this div. */}
        <div ref={mapContainerRef} className="map-container" aria-label="Interactive map" />

        {/* Loading and error messages for the TANTALIS lookup. Only shown when there is a message.
            role="status" lets screen readers announce it. */}
        {previewStatus && (
          <div className="map-preview-status" role="status" aria-live="polite">
            {previewStatus}
          </div>
        )}

        {/* Toolbar on the right side of the map. */}
        <div className="map-controls map-controls--right">
          {/* Zoom in and zoom out buttons. */}
          <div className="map-zoom-panel">
            <button type="button" onClick={() => zoomBy(1)} aria-label="Zoom in" title="Zoom in">
              +
            </button>
            <button type="button" onClick={() => zoomBy(-1)} aria-label="Zoom out" title="Zoom out">
              −
            </button>
          </div>

          {/* Basemap button and its picker. */}
          <div className="map-basemap-wrap">
            {/* Opens or closes the picker. aria-expanded tells screen readers if it's open. */}
            <button
              type="button"
              className="map-tool-toggle map-basemap-toggle"
              aria-expanded={showBasemapPanel}
              aria-controls="basemap-panel"
              onClick={() => setShowBasemapPanel((isOpen) => !isOpen)}
            >
              <span className="map-tool-toggle__icon" aria-hidden="true">
                <PaperMapIcon />
              </span>
              <span className="map-tool-toggle__label">Basemap</span>
            </button>

            {/* The picker. Only shown when open. */}
            {showBasemapPanel && (
              <div id="basemap-panel" className="basemap-panel" role="group" aria-label="Basemap options">
                {/* Picker title and close button. */}
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

                {/* Street option. Checked when street is selected. */}
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

                {/* Satellite option. Checked when satellite is selected. */}
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

          {/* Shape symbology button. Only shown after the form has sent a TANTALIS lookup. */}
          {tantalisPreview && (
            <div className="map-shape-symbology-wrap">
              {/* Opens or closes the colour/transparency panel. */}
              <button
                type="button"
                className="map-tool-toggle"
                aria-expanded={showShapeSymbologyPanel}
                aria-controls="shape-symbology-panel"
                onClick={() => setShowShapeSymbologyPanel((isOpen) => !isOpen)}
              >
                <span className="map-tool-toggle__icon" aria-hidden="true">
                  <PaintbrushIcon />
                </span>
                <span className="map-tool-toggle__label">Shape symbology</span>
              </button>

              {/* The panel. Only shown when open. */}
              {showShapeSymbologyPanel && (
                <div
                  id="shape-symbology-panel"
                  className="map-preview-style-panel"
                  role="group"
                  aria-label="Shape symbology"
                >
                  {/* Colour slider: moves around the colour wheel (0-360). */}
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

                  {/* Transparency slider: 0% = solid, 100% = invisible. */}
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
