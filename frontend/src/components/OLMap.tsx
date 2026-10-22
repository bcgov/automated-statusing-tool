// React tools:
// useEffect = run code after the page draws (for example, set up the map).
// useRef = keep a value between redraws without causing a redraw.
// useState = store a value that redraws the page when it changes.
import { useEffect, useRef, useState } from "react";
// FC = "function component". Used here only as a type, so it adds nothing to the final app.
import type { FC, FormEvent } from "react";
// OpenLayers pieces used to build the map.
import Map from "ol/Map";
import View from "ol/View"; // Controls where the map looks (center and zoom)
import LayerGroup from "ol/layer/Group";
import TileLayer from "ol/layer/Tile"; // Layer for basemap image tiles
import VectorLayer from "ol/layer/Vector"; // Layer for shapes (Tantalis preview)
import XYZ from "ol/source/XYZ"; // Loads tiles from a URL pattern like {z}/{y}/{x}
import TileWMS from "ol/source/TileWMS";
import VectorSource from "ol/source/Vector"; // Holds the shapes shown in a vector layer
import { GeoJSON } from "ol/format"; // Reads and writes GeoJSON shapes
import { fromLonLat } from "ol/proj"; // Converts longitude/latitude into map coordinates
import { Fill, Stroke, Style } from "ol/style"; // Fill colour, outline and full shape style
import Attribution from "ol/control/Attribution";
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
const TANTALIS_WMS_URL = "https://openmaps.gov.bc.ca/geo/pub/ows";
// The Tantalis Crown tenures layer to search.
const TANTALIS_LAYER = "pub:WHSE_TANTALIS.TA_CROWN_TENURES_SVW";

// Credit shown for the Esri basemap tiles.
const ESRI_ATTRIBUTION = "Tiles © Esri";
const TANTALIS_ATTRIBUTION = "Data from the Province of British Columbia";

interface MapLayerDefinition {
  name: string;
  label: string;
  idAttribute: { name: string; label: string; type: "text" | "number" };
  styles: TantalisStyleDefinition[];
  queryAttributes: TantalisQueryAttribute[];
}

interface TantalisStyleDefinition {
  name: string;
  label: string;
}

interface TantalisQueryAttribute {
  name: string;
  label: string;
  type: "text" | "number" | "date";
}

interface MapLayerGroupDefinition {
  id: string;
  label: string;
  layers: MapLayerDefinition[];
}

// Layer definitions drive map overlays and their layer-specific query controls.
const MAP_LAYER_GROUPS: MapLayerGroupDefinition[] = [
  {
    id: "crown-land",
    label: "Crown land",
    layers: [
      {
        name: TANTALIS_LAYER,
        label: "Crown tenures",
        idAttribute: { name: "OBJECTID", label: "Object ID", type: "number" },
        styles: [
          { name: "2214", label: "Outlined" },
          { name: "2215", label: "Colour Filled" },
        ],
        queryAttributes: [
          { name: "CROWN_LANDS_FILE", label: "File number", type: "text" },
          { name: "DISPOSITION_TRANSACTION_SID", label: "Disposition ID", type: "number" },
          { name: "INTRID_SID", label: "Parcel ID", type: "number" },
          { name: "TENURE_STAGE", label: "Tenure stage", type: "text" },
          { name: "TENURE_STATUS", label: "Tenure status", type: "text" },
          { name: "TENURE_TYPE", label: "Tenure type", type: "text" },
          { name: "TENURE_SUBTYPE", label: "Tenure subtype", type: "text" },
          { name: "TENURE_PURPOSE", label: "Tenure purpose", type: "text" },
          { name: "TENURE_SUBPURPOSE", label: "Tenure subpurpose", type: "text" },
          { name: "APPLICATION_TYPE_CDE", label: "Application type", type: "text" },
          { name: "TENURE_DOCUMENT", label: "Tenure document", type: "text" },
          { name: "TENURE_EXPIRY", label: "Expiry date", type: "date" },
          { name: "TENURE_LOCATION", label: "Tenure location", type: "text" },
          { name: "RESPONSIBLE_BUSINESS_UNIT", label: "Responsible business unit", type: "text" },
          { name: "FEATURE_CODE", label: "Feature code", type: "text" },
        ],
      },
      {
        name: "pub:WHSE_TANTALIS.TA_CROWN_INVENTORY_SVW",
        label: "Crown land inventory",
        idAttribute: { name: "OBJECTID", label: "Object ID", type: "number" },
        styles: [
          { name: "2173", label: "Outlined" },
          { name: "2174", label: "Colour Filled" },
        ],
        queryAttributes: [
          { name: "INTRID_SID", label: "Parcel ID", type: "number" },
          { name: "TENURE_STAGE", label: "Tenure stage", type: "text" },
          { name: "TENURE_STATUS", label: "Tenure status", type: "text" },
          { name: "TENURE_TYPE", label: "Tenure type", type: "text" },
          { name: "TENURE_SUBTYPE", label: "Tenure subtype", type: "text" },
          { name: "TENURE_PURPOSE", label: "Tenure purpose", type: "text" },
          { name: "TENURE_SUBPURPOSE", label: "Tenure subpurpose", type: "text" },
          { name: "CROWN_LANDS_FILE", label: "File number", type: "text" },
          { name: "TENURE_DOCUMENT", label: "Tenure document", type: "text" },
          { name: "TENURE_EXPIRY", label: "Expiry date", type: "date" },
          { name: "TENURE_LOCATION", label: "Tenure location", type: "text" },
          { name: "RESPONSIBLE_BUSINESS_UNIT", label: "Responsible business unit", type: "text" },
          { name: "DISPOSITION_TRANSACTION_SID", label: "Disposition ID", type: "number" },
          { name: "FEATURE_CODE", label: "Feature code", type: "text" },
        ],
      },
    ],
  },
  {
    id: "critical-overlaps",
    label: "Critical overlaps",
    layers: [
      {
        name: "pub:WHSE_LEGAL_ADMIN_BOUNDARIES.FNT_TREATY_RELATED_LAND_SP",
        label: "FCBC treaty-related lands",
        idAttribute: { name: "OBJECTID", label: "Object ID", type: "number" },
        styles: [
          { name: "217", label: "Outlined" },
          { name: "218", label: "Colour Filled" },
        ],
        queryAttributes: [
          { name: "TREATY_RELATED_LAND_ID", label: "Treaty-related land ID", type: "number" },
          { name: "TREATY", label: "Treaty", type: "text" },
          { name: "EFFECTIVE_DATE", label: "Effective date", type: "date" },
          { name: "FIRST_NATION_NAME", label: "First Nation name", type: "text" },
          { name: "LAND_TYPE", label: "Land type", type: "text" },
          { name: "CHAPTER_REFERENCE", label: "Chapter reference", type: "text" },
          { name: "APPENDIX_REFERENCE", label: "Appendix reference", type: "text" },
          { name: "COMMENTS", label: "Comments", type: "text" },
          { name: "FEATURE_CODE", label: "Feature code", type: "text" },
          { name: "FEATURE_AREA_SQM", label: "Feature area (m²)", type: "number" },
          { name: "FEATURE_LENGTH_M", label: "Feature length (m)", type: "number" },
        ],
      },
    ],
  },
];

interface TantalisQueryResult {
  objectId: string;
  layerName: string;
  idAttribute: MapLayerDefinition["idAttribute"];
  queryAttributeName: string;
  attributes: Array<{ name: string; label: string; value: string }>;
}

interface TantalisQueryResponse {
  features: Array<{ properties: Record<string, unknown> | null }>;
  numberMatched?: number | string;
}

const TANTALIS_QUERY_RESULT_LIMIT = 10;
// Builds a basemap tile source from a tile URL.
// crossOrigin lets the browser use tiles from another website safely.
const createBasemapSource = (url: string): XYZ =>
  new XYZ({ url, crossOrigin: "anonymous", attributions: ESRI_ATTRIBUTION });

const asText = (value: unknown): string => (value == null ? "" : String(value));

const isTantalisQueryResponse = (value: unknown): value is TantalisQueryResponse =>
  typeof value === "object" &&
  value !== null &&
  "features" in value &&
  Array.isArray(value.features);

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

// Icon for the Layers button (stacked map layers).
const LayersIcon: FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path
      d="M12 3L3 7.5L12 12L21 7.5L12 3ZM3 12L12 16.5L21 12M3 16.5L12 21L21 16.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
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
  const mapFrameRef = useRef<HTMLDivElement | null>(null);
  const mapControlsRef = useRef<HTMLDivElement | null>(null);
  const layerPanelRef = useRef<HTMLDivElement | null>(null);
  // The OpenLayers map, so every part of this file can reach it.
  const mapRef = useRef<Map | null>(null);
  // The layer showing the current TANTALIS preview shape, so the sliders can restyle it.
  const previewLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  // References let the layer panel update individual OpenLayers WMS layers.
  const tantalisLayerRefs = useRef<Record<string, TileLayer<TileWMS>>>({});
  const layerGroupToggleRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const queryHighlightLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const queryAbortRef = useRef<AbortController | null>(null);

  // Which basemap is selected. Starts on satellite.
  const [selectedBasemap, setSelectedBasemap] = useState<BasemapId>("satellite");
  // One active popup keeps map tools from stacking on top of each other.
  const [openMapPanel, setOpenMapPanel] = useState<"basemap" | "layers" | null>(null);
  const [layerPanelMaxHeight, setLayerPanelMaxHeight] = useState<number>();
  // The active layer is the most recently enabled layer and receives symbology/query actions.
  const [activeTantalisLayer, setActiveTantalisLayer] = useState<string>(TANTALIS_LAYER);
  const [selectedTantalisStyles, setSelectedTantalisStyles] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      MAP_LAYER_GROUPS.flatMap((group) => group.layers.map((layer) => [layer.name, layer.styles[0]?.name ?? ""]))
    )
  );
  const [selectedQueryAttributes, setSelectedQueryAttributes] = useState<Record<string, string>>({});
  const [queryAttributeValues, setQueryAttributeValues] = useState<Record<string, string>>({});
  const [queryResults, setQueryResults] = useState<TantalisQueryResult[]>([]);
  const [queryStatus, setQueryStatus] = useState<string>("");
  const [isQuerying, setIsQuerying] = useState<boolean>(false);
  const [zoomingObjectId, setZoomingObjectId] = useState<string | null>(null);
  // Keep the sample overlays off until the user enables them.
  const [visibleTantalisLayers, setVisibleTantalisLayers] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(MAP_LAYER_GROUPS.flatMap((group) => group.layers.map((layer) => [layer.name, false])))
  );
  // Current colour slider value.
  const [previewHue, setPreviewHue] = useState<number>(DEFAULT_PREVIEW_HUE);
  // Current transparency slider value.
  const [previewOpacity, setPreviewOpacity] = useState<number>(DEFAULT_PREVIEW_OPACITY);
  // Message shown on the map while loading, or when the lookup fails or finds nothing.
  // An empty string means no message is shown.
  const [previewStatus, setPreviewStatus] = useState<string>("");

  const toggleMapPanel = (panel: "basemap" | "layers"): void => {
    setOpenMapPanel((current) => (current === panel ? null : panel));
  };

  useEffect(() => {
    if (openMapPanel !== "layers") {
      return;
    }

    const panel = layerPanelRef.current;
    const frame = mapFrameRef.current;
    const controls = mapControlsRef.current;
    if (!panel || !frame || !controls) {
      return;
    }

    let observedFooter: HTMLElement | null = null;
    let resizeObserver: ResizeObserver | undefined;
    const updateLayerPanelHeight = (): void => {
      const footer = document.querySelector<HTMLElement>(".bcgov-page-footer");
      const panelTop = panel.getBoundingClientRect().top;
      const availableBottom = footer?.getBoundingClientRect().top ?? window.innerHeight;
      const availableHeight = Math.max(0, availableBottom - panelTop - 8);
      setLayerPanelMaxHeight(Math.min(380, availableHeight));
      if (footer !== observedFooter) {
        if (observedFooter) {
          resizeObserver?.unobserve(observedFooter);
        }
        observedFooter = footer;
        if (footer) {
          resizeObserver?.observe(footer);
        }
      }
    };

    resizeObserver = new ResizeObserver(updateLayerPanelHeight);
    resizeObserver.observe(frame);
    resizeObserver.observe(controls);
    const mutationObserver = new MutationObserver(updateLayerPanelHeight);
    mutationObserver.observe(document.querySelector("#root") ?? document.body, {
      childList: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    window.addEventListener("resize", updateLayerPanelHeight);
    updateLayerPanelHeight();

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      window.removeEventListener("resize", updateLayerPanelHeight);
    };
  }, [openMapPanel]);

  const selectQueryLayer = (layerName: string): void => {
    queryAbortRef.current?.abort();
    queryAbortRef.current = null;
    setIsQuerying(false);
    setZoomingObjectId(null);
    setActiveTantalisLayer(layerName);
    setQueryResults([]);
    setQueryStatus("");
    queryHighlightLayerRef.current?.getSource()?.clear();
  };

  // 1. Create the map one time when the component first appears.
  useEffect(() => {
    // Stop if the <div> isn't ready yet, or the map already exists.
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    // Basemap layer. Starts on satellite to match the selected option.
    const baseLayer = new TileLayer({ source: createBasemapSource(SATELLITE_URL) });

    // Create a real OpenLayers group so these related WMS overlays remain grouped on the map.
    const mapLayerGroups = MAP_LAYER_GROUPS.map((group) => {
      const layers = group.layers.map((layer) => {
        const mapLayer = new TileLayer({
          visible: false,
          source: new TileWMS({
            url: TANTALIS_WMS_URL,
            params: { LAYERS: layer.name, TILED: true },
            serverType: "geoserver",
            crossOrigin: "anonymous",
            attributions: TANTALIS_ATTRIBUTION,
          }),
        });
        tantalisLayerRefs.current[layer.name] = mapLayer;
        return mapLayer;
      });

      return new LayerGroup({ layers, properties: { title: group.label } });
    });

    const map = new Map({
      target: mapContainerRef.current, // Draw the map inside our <div>
      layers: [baseLayer, ...mapLayerGroups],
      view: new View({ center: fromLonLat(center), zoom }),
      controls: [], // Hide the default OpenLayers buttons. We use our own.
    });

    // Query results draw only the one feature the user chooses, not the full WMS layer.
    const queryHighlightLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        fill: new Fill({ color: "rgba(255, 193, 7, 0.28)" }),
        stroke: new Stroke({ color: "#b45309", width: 3 }),
      }),
      zIndex: 110,
    });
    map.addLayer(queryHighlightLayer);
    queryHighlightLayerRef.current = queryHighlightLayer;

    // Keep provider credits available while using custom map controls.
    map.addControl(new Attribution({ collapsible: true, collapsed: true }));

    // Add the scale bar in metres/kilometres.
    // The class name matches the existing CSS that positions and styles it.
    map.addControl(new ScaleLine({ className: "map-scale", units: "metric", minWidth: 140 }));

    // Save the map so the rest of the file can use it.
    mapRef.current = map;

    // Clean up when the component is removed from the page.
    return () => {
      queryAbortRef.current?.abort();
      map.setTarget(undefined);
      mapRef.current = null;
      queryHighlightLayerRef.current = null;
    };
    // The empty list [] means this runs only once. Later center/zoom changes are handled in step 2.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync WMS layer visibility and the group's partial-selection checkbox state.
  useEffect(() => {
    Object.entries(visibleTantalisLayers).forEach(([name, isVisible]) => {
      tantalisLayerRefs.current[name]?.setVisible(isVisible);
    });

    MAP_LAYER_GROUPS.forEach((group) => {
      const enabledCount = group.layers.filter((layer) => visibleTantalisLayers[layer.name]).length;
      const groupToggle = layerGroupToggleRefs.current[group.id];
      if (groupToggle) {
        groupToggle.indeterminate = enabledCount > 0 && enabledCount < group.layers.length;
      }
    });
  }, [visibleTantalisLayers]);

  // Apply each overlay's own published WMS style without changing its visibility.
  useEffect(() => {
    Object.entries(tantalisLayerRefs.current).forEach(([name, layer]) => {
      layer.getSource()?.updateParams({ STYLES: selectedTantalisStyles[name] ?? "" });
    });
  }, [selectedTantalisStyles]);

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

  // Search only attribute fields first; the WMS overlay stays hidden unless its checkbox is enabled.
  const searchTantalisLayer = async (
    event: FormEvent<HTMLFormElement>,
    targetLayer: MapLayerDefinition,
    attributeFilter: { attribute: TantalisQueryAttribute; value: string }
  ): Promise<void> => {
    event.preventDefault();
    queryAbortRef.current?.abort();
    queryAbortRef.current = null;
    setIsQuerying(false);
    setActiveTantalisLayer(targetLayer.name);
    const attributeValue = attributeFilter.value.trim();

    if (attributeFilter.attribute.type === "number" && !isDigitsOnly(attributeValue)) {
      setQueryStatus(`${attributeFilter.attribute.label} must contain numbers only.`);
      setQueryResults([]);
      return;
    }
    if (!attributeValue) {
      setQueryStatus(`Enter a value for ${attributeFilter.attribute.label}.`);
      setQueryResults([]);
      return;
    }

    const controller = new AbortController();
    queryAbortRef.current = controller;
    setQueryResults([]);
    setQueryStatus(`Searching ${targetLayer.label}...`);
    setIsQuerying(true);

    const value =
      attributeFilter.attribute.type === "number" ? attributeValue : `'${escapeCqlText(attributeValue)}'`;

    const url = new URL(TANTALIS_WFS_URL);
    url.searchParams.set("service", "WFS");
    url.searchParams.set("version", "2.0.0");
    url.searchParams.set("request", "GetFeature");
    url.searchParams.set("typeNames", targetLayer.name);
    url.searchParams.set("outputFormat", "application/json");
    url.searchParams.set("srsName", "EPSG:4326");
    url.searchParams.set("CQL_FILTER", `${attributeFilter.attribute.name}=${value}`);
    url.searchParams.set("count", String(TANTALIS_QUERY_RESULT_LIMIT));
    url.searchParams.set(
      "propertyName",
      [targetLayer.idAttribute.name, ...targetLayer.queryAttributes.map((attribute) => attribute.name)].join(",")
    );

    try {
      const response = await fetch(url.toString(), { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`the map service returned status ${response.status}`);
      }

      const payload: unknown = await response.json();
      if (!isTantalisQueryResponse(payload)) {
        throw new Error("the map service returned an unexpected search response");
      }

      const results = payload.features.map((feature): TantalisQueryResult => {
        const properties = feature.properties;
        const objectId = asText(properties?.[targetLayer.idAttribute.name]);
        if (
          !objectId ||
          (targetLayer.idAttribute.type === "number" && !isDigitsOnly(objectId))
        ) {
          throw new Error("a search result did not include a valid feature identifier");
        }

        return {
          objectId,
          layerName: targetLayer.name,
          idAttribute: targetLayer.idAttribute,
          queryAttributeName: attributeFilter.attribute.name,
          attributes: targetLayer.queryAttributes.map((attribute) => ({
            name: attribute.name,
            label: attribute.label,
            value: asText(properties?.[attribute.name]),
          })),
        };
      });
      setQueryResults(results);

      const numberMatched = Number(payload.numberMatched);
      const hasKnownTotal = Number.isFinite(numberMatched);
      if (results.length === 0) {
        setQueryStatus("No matching features found.");
      } else if (hasKnownTotal && numberMatched > results.length) {
        setQueryStatus(
          `Showing the first ${results.length} of ${numberMatched} matches. Refine the identifiers to narrow the results.`
        );
      } else if (results.length === TANTALIS_QUERY_RESULT_LIMIT) {
        setQueryStatus(`Showing up to ${results.length} matches. Refine the identifiers to narrow the results.`);
      } else {
        setQueryStatus(`${results.length} ${results.length === 1 ? "match" : "matches"} found.`);
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      const reason = error instanceof Error ? error.message : "unknown error";
      setQueryStatus(`Could not search TANTALIS: ${reason}.`);
    } finally {
      if (queryAbortRef.current === controller) {
        queryAbortRef.current = null;
        setIsQuerying(false);
      }
    }
  };

  // Fetch geometry only for the chosen result, then highlight and zoom to that feature.
  const zoomToQueryResult = async (result: TantalisQueryResult): Promise<void> => {
    queryAbortRef.current?.abort();
    const controller = new AbortController();
    queryAbortRef.current = controller;
    setZoomingObjectId(result.objectId);
    setQueryStatus("Loading selected feature geometry...");

    const url = new URL(TANTALIS_WFS_URL);
    url.searchParams.set("service", "WFS");
    url.searchParams.set("version", "2.0.0");
    url.searchParams.set("request", "GetFeature");
    url.searchParams.set("typeNames", result.layerName);
    url.searchParams.set("outputFormat", "application/json");
    url.searchParams.set("srsName", "EPSG:4326");
    const objectIdValue =
      result.idAttribute.type === "number" ? result.objectId : `'${escapeCqlText(result.objectId)}'`;
    url.searchParams.set("CQL_FILTER", `${result.idAttribute.name}=${objectIdValue}`);
    url.searchParams.set("count", "1");

    try {
      const response = await fetch(url.toString(), { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`the map service returned status ${response.status}`);
      }

      const geoJson: unknown = await response.json();
      if (!isTantalisQueryResponse(geoJson) || geoJson.features.length === 0) {
        throw new Error("the selected feature geometry was not returned");
      }
      const features = new GeoJSON().readFeatures(geoJson, {
        dataProjection: "EPSG:4326",
        featureProjection: "EPSG:3857",
      }) as Feature[];
      const source = queryHighlightLayerRef.current?.getSource();
      const map = mapRef.current;
      if (!source || !map) {
        throw new Error("the map is not ready to display the selected feature");
      }

      source.clear();
      source.addFeatures(features);
      const extent = source.getExtent();
      if (!extent || !extent.every(Number.isFinite)) {
        throw new Error("the selected feature has no usable geometry");
      }

      map.getView().fit(extent, { padding: [36, 36, 36, 36], maxZoom: 16, duration: 600 });
      setQueryStatus("Zoomed to the selected feature. The full layer remains off unless enabled.");
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      const reason = error instanceof Error ? error.message : "unknown error";
      setQueryStatus(`Could not load selected feature: ${reason}.`);
    } finally {
      if (queryAbortRef.current === controller) {
        queryAbortRef.current = null;
        setZoomingObjectId(null);
      }
    }
  };

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
      <div className="map-frame" ref={mapFrameRef}>
        {/* OpenLayers draws the map inside this div. */}
        <div ref={mapContainerRef} className="map-container" aria-label="Interactive map" />

        {/* Loading and error messages for the TANTALIS lookup. Only shown when there is a message.
            role="status" lets screen readers announce it. */}
        {previewStatus && (
          <div className="map-preview-status" role="status" aria-live="polite">
            {previewStatus}
          </div>
        )}

        {/* Compact, bordered tool panel; each action remains a distinct button. */}
        <div className="map-controls map-controls--right" ref={mapControlsRef}>
          {/* Zoom in and zoom out buttons. */}
          <div className="map-zoom-panel">
            <button type="button" onClick={() => zoomBy(1)} aria-label="Zoom in" title="Zoom in">
              +
            </button>
            <button type="button" onClick={() => zoomBy(-1)} aria-label="Zoom out" title="Zoom out">
              −
            </button>
          </div>

          {/* Selecting a tool closes the previously open popup. */}
          <div className="map-basemap-wrap">
            <button
              type="button"
              className="map-tool-toggle map-basemap-toggle"
              aria-label="Basemap"
              aria-expanded={openMapPanel === "basemap"}
              aria-controls="basemap-panel"
              onClick={() => toggleMapPanel("basemap")}
            >
              <span className="map-tool-toggle__icon" aria-hidden="true">
                <PaperMapIcon />
              </span>
            </button>

            {/* The picker. Only shown when open. */}
            {openMapPanel === "basemap" && (
              <div id="basemap-panel" className="basemap-panel" role="group" aria-label="Basemap options">
                {/* Picker title and close button. */}
                <div className="basemap-panel__header">
                  <span>Select map</span>
                  <button
                    type="button"
                    aria-label="Close basemap options"
                    title="Close basemap options"
                    onClick={() => setOpenMapPanel(null)}
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

          {/* Each layer checkbox controls its own visibility; enabling one also makes it active. */}
          <div className="map-layers-wrap">
            <button
              type="button"
              className="map-tool-toggle map-layer-toggle"
              aria-label="Layers"
              aria-expanded={openMapPanel === "layers"}
              aria-controls="layer-panel"
              onClick={() => toggleMapPanel("layers")}
            >
              <span className="map-tool-toggle__icon" aria-hidden="true">
                <LayersIcon />
              </span>
            </button>

            {openMapPanel === "layers" && (
              <div
                id="layer-panel"
                className="map-layer-panel"
                role="group"
                aria-label="Map layers"
                ref={layerPanelRef}
                style={{ maxHeight: layerPanelMaxHeight }}
              >
                <div className="map-layer-panel__title">Map layers</div>
                {MAP_LAYER_GROUPS.map((group) => {
                  const enabledCount = group.layers.filter((layer) => visibleTantalisLayers[layer.name]).length;

                  return (
                    <fieldset className="map-layer-group" key={group.id}>
                      <legend>{group.label}</legend>
                      <label className="map-layer-option map-layer-option--group">
                        <input
                          ref={(element) => {
                            layerGroupToggleRefs.current[group.id] = element;
                          }}
                          type="checkbox"
                          checked={enabledCount === group.layers.length}
                          aria-label={`Toggle all ${group.label} layers`}
                          onChange={(event) => {
                            const isVisible = event.currentTarget.checked;
                            setVisibleTantalisLayers((current) => ({
                              ...current,
                              ...Object.fromEntries(group.layers.map((layer) => [layer.name, isVisible])),
                            }));
                          }}
                        />
                        <span>Show all</span>
                      </label>
                      {group.layers.map((layer) => {
                        const selectedAttribute = layer.queryAttributes.find(
                          (attribute) => attribute.name === selectedQueryAttributes[layer.name]
                        );
                        return (
                          <div className="map-layer-entry" key={layer.name}>
                            <div className="map-layer-row">
                              <label className="map-layer-option map-layer-option--active">
                                <input
                                  type="checkbox"
                                  checked={visibleTantalisLayers[layer.name]}
                                  aria-label={`Toggle ${layer.label} layer`}
                                  onChange={(event) => {
                                    const isVisible = event.currentTarget.checked;
                                    setVisibleTantalisLayers((current) => ({ ...current, [layer.name]: isVisible }));
                                    if (isVisible) {
                                      selectQueryLayer(layer.name);
                                    }
                                  }}
                                />
                                <span className="map-layer-name">{layer.label}</span>
                              </label>
                            </div>
                            {visibleTantalisLayers[layer.name] && (
                              <form
                                className="map-layer-filter-row"
                                onSubmit={(event) => {
                                  if (!selectedAttribute) {
                                    event.preventDefault();
                                    return;
                                  }
                                  void searchTantalisLayer(event, layer, {
                                    attribute: selectedAttribute,
                                    value: queryAttributeValues[layer.name] ?? "",
                                  });
                                }}
                              >
                                <select
                                  className="map-layer-style-select"
                                  aria-label="Symbology"
                                  title="Symbology"
                                  value={selectedTantalisStyles[layer.name] ?? ""}
                                  onChange={(event) => {
                                    const styleName = event.currentTarget.value;
                                    setSelectedTantalisStyles((current) => ({
                                      ...current,
                                      [layer.name]: styleName,
                                    }));
                                  }}
                                >
                                  {layer.styles.map((style) => (
                                    <option value={style.name} key={style.name || "default"}>
                                      {style.label}
                                    </option>
                                  ))}
                                </select>
                                <select
                                  aria-label={`${layer.label} query field`}
                                  title={`${layer.label} query fields`}
                                  value={selectedQueryAttributes[layer.name] ?? ""}
                                  onChange={(event) => {
                                    const attributeName = event.currentTarget.value;
                                    setSelectedQueryAttributes((current) => ({
                                      ...current,
                                      [layer.name]: attributeName,
                                    }));
                                  }}
                                >
                                  <option value="">Choose a field...</option>
                                  {layer.queryAttributes.map((attribute) => (
                                    <option value={attribute.name} key={attribute.name}>
                                      {attribute.label}
                                    </option>
                                  ))}
                                </select>
                                <input
                                  type={selectedAttribute?.type === "date" ? "date" : "text"}
                                  inputMode={selectedAttribute?.type === "number" ? "numeric" : undefined}
                                  aria-label={`${layer.label} ${selectedAttribute?.label ?? "attribute"} value`}
                                  placeholder={selectedAttribute?.label ?? "Value"}
                                  value={queryAttributeValues[layer.name] ?? ""}
                                  disabled={!selectedAttribute}
                                  onChange={(event) => {
                                    const attributeValue = event.currentTarget.value;
                                    setQueryAttributeValues((current) => ({
                                      ...current,
                                      [layer.name]: attributeValue,
                                    }));
                                  }}
                                />
                                <button
                                  type="submit"
                                  className="map-layer-filter-submit tantalis-preview-link"
                                  aria-label="Search and Zoom to Layer"
                                  title="Search and Zoom to Layer"
                                  disabled={
                                    !selectedQueryAttributes[layer.name] ||
                                    !queryAttributeValues[layer.name]?.trim() ||
                                    isQuerying
                                  }
                                >
                                  <span>Search and</span>
                                  <span>Zoom to Layer</span>
                                </button>
                              </form>
                            )}
                            {visibleTantalisLayers[layer.name] && tantalisPreview && layer.name === TANTALIS_LAYER && (
                              <details className="map-query-symbology">
                                <summary>Preview symbology</summary>
                                <label className="map-preview-control">
                                  <span>Colour</span>
                                  <input
                                    type="range"
                                    min="0"
                                    max="360"
                                    value={previewHue}
                                    onChange={(event) => setPreviewHue(Number(event.currentTarget.value))}
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
                                    onChange={(event) => setPreviewOpacity(Number(event.currentTarget.value))}
                                    className="map-preview-transparency-slider"
                                  />
                                </label>
                              </details>
                            )}
                            {visibleTantalisLayers[layer.name] && activeTantalisLayer === layer.name && queryStatus && (
                              <div className="map-query-status" role="status" aria-live="polite">
                                {queryStatus}
                              </div>
                            )}
                            {visibleTantalisLayers[layer.name] &&
                              activeTantalisLayer === layer.name &&
                              queryResults.length > 0 && (
                              <ul className="map-query-results">
                                {queryResults.map((result) => {
                                  const primaryAttribute =
                                    result.attributes.find(
                                      (attribute) =>
                                        attribute.name === result.queryAttributeName && attribute.value
                                    ) ?? result.attributes.find((attribute) => attribute.value);
                                  const additionalAttributes = result.attributes
                                    .filter(
                                      (attribute) =>
                                        attribute.value && attribute.name !== primaryAttribute?.name
                                    )
                                    .slice(0, 3);

                                  return (
                                    <li key={`${result.layerName}-${result.objectId}`}>
                                      <div className="map-query-result__details">
                                        <strong>
                                          {primaryAttribute
                                            ? `${primaryAttribute.label}: ${primaryAttribute.value}`
                                            : `${result.idAttribute.label}: ${result.objectId}`}
                                        </strong>
                                        {additionalAttributes.map((attribute) => (
                                          <span key={attribute.name}>
                                            {attribute.label}: {attribute.value}
                                          </span>
                                        ))}
                                      </div>
                                      <button
                                        type="button"
                                        className="map-query-zoom"
                                        disabled={zoomingObjectId !== null}
                                        onClick={() => void zoomToQueryResult(result)}
                                      >
                                        {zoomingObjectId === result.objectId ? "Loading..." : "Zoom to"}
                                      </button>
                                    </li>
                                  );
                                })}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                    </fieldset>
                  );
                })}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
};

export default OLMap;
