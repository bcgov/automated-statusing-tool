// React tools:
// useEffect = run code after the page draws (for example, set up the map).
// useRef = keep a value between redraws without causing a redraw.
// useState = store a value that redraws the page when it changes.
import { useCallback, useEffect, useRef, useState } from "react";
// FC = "function component". Used here only as a type, so it adds nothing to the final app.
import type { FC, FormEvent, RefObject } from "react";
// OpenLayers pieces used to build the map.
import Map from "ol/Map";
import View from "ol/View"; // Controls where the map looks (center and zoom)
import LayerGroup from "ol/layer/Group";
import TileLayer from "ol/layer/Tile"; // Layer for basemap image tiles
import VectorLayer from "ol/layer/Vector"; // Layer for shapes (Tantalis preview)
import XYZ from "ol/source/XYZ"; // Loads tiles from a URL pattern like {z}/{y}/{x}
import TileWMS from "ol/source/TileWMS";
import VectorSource from "ol/source/Vector"; // Holds the shapes shown in a vector layer
import { GeoJSON, WKT } from "ol/format";
import { fromLonLat, transformExtent } from "ol/proj"; // Converts coordinates and layer extents
import { Fill, Stroke, Style } from "ol/style"; // Fill colour, outline and full shape style
import { createEmpty, extend as extendExtent } from "ol/extent";
import ScaleLine from "ol/control/ScaleLine"; // The scale bar
import { unByKey } from "ol/Observable"; // Removes an event listener that was added with map.on()
// Feature = one shape on the map. Used only as a type.
import type Feature from "ol/Feature";
import type {
  CriticalConflictError,
  CriticalConflictLayer,
  CriticalConflictsRequest,
  TantalisIdentifiers,
} from "../types/tantalis";
import CriticalConflictsPanel from "./CriticalConflictsPanel";

// Default OpenLayers styling.
import "ol/ol.css";

// The only two basemap choices.
type BasemapId = "street" | "satellite";

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
  onShapeLoaded: (isLoaded: boolean) => void;
  criticalConflictsRequest: CriticalConflictsRequest | null;
  isCriticalConflictsOpen: boolean;
  onCloseCriticalConflicts: () => void;
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

type QueryOperator = "<" | "<=" | "=" | ">=" | ">" | "<>";

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
        label: "Crown Tenures",
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
        label: "Crown Land Inventory",
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
    label: "FCBC Critical Overlaps",
    layers: [
      {
        name: "pub:WHSE_LEGAL_ADMIN_BOUNDARIES.FNT_TREATY_RELATED_LAND_SP",
        label: "FCBC Treaty-Related Lands",
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

interface CriticalLayerCheck {
  layer: MapLayerDefinition;
  features: Feature[];
  status: "success" | "error";
  message?: string;
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

const readWmsLayerExtent = async (layerName: string, signal: AbortSignal): Promise<number[]> => {
  const url = new URL(TANTALIS_WMS_URL);
  url.searchParams.set("service", "WMS");
  url.searchParams.set("version", "1.3.0");
  url.searchParams.set("request", "GetCapabilities");

  const response = await fetch(url.toString(), { signal });
  if (!response.ok) {
    throw new Error(`WMS capabilities returned status ${response.status}`);
  }
  const xml = new DOMParser().parseFromString(await response.text(), "application/xml");
  if (xml.querySelector("parsererror")) {
    throw new Error("the WMS capabilities were not valid XML");
  }

  const layer = Array.from(xml.getElementsByTagNameNS("*", "Layer")).find((element) =>
    Array.from(element.children).some(
      (child) => child.localName === "Name" && child.textContent?.trim() === layerName
    )
  );
  if (!layer) {
    throw new Error("the layer extent was not found in WMS capabilities");
  }

  const boundingBoxes = Array.from(layer.children).filter((child) => child.localName === "BoundingBox");
  const mercatorBox = boundingBoxes.find(
    (box) => box.getAttribute("CRS") === "EPSG:3857" || box.getAttribute("SRS") === "EPSG:3857"
  );
  const geographicBox = Array.from(layer.children).find((child) => child.localName === "EX_GeographicBoundingBox");
  const selectedBox = mercatorBox ?? boundingBoxes.find((box) =>
    ["CRS:84", "EPSG:4326"].includes(box.getAttribute("CRS") ?? box.getAttribute("SRS") ?? "")
  );

  if (mercatorBox) {
    const extent = [
      Number(mercatorBox.getAttribute("minx")),
      Number(mercatorBox.getAttribute("miny")),
      Number(mercatorBox.getAttribute("maxx")),
      Number(mercatorBox.getAttribute("maxy")),
    ];
    if (extent.every(Number.isFinite)) {
      return extent;
    }
  }

  if (selectedBox) {
    const crs = selectedBox.getAttribute("CRS") ?? selectedBox.getAttribute("SRS");
    const values = [
      Number(selectedBox.getAttribute("minx")),
      Number(selectedBox.getAttribute("miny")),
      Number(selectedBox.getAttribute("maxx")),
      Number(selectedBox.getAttribute("maxy")),
    ];
    if (values.every(Number.isFinite)) {
      const geographicExtent = crs === "EPSG:4326"
        ? [values[1], values[0], values[3], values[2]]
        : values;
      return transformExtent(geographicExtent, "EPSG:4326", "EPSG:3857");
    }
  }

  if (geographicBox) {
    const readValue = (name: string): number =>
      Number(geographicBox.getElementsByTagNameNS("*", name)[0]?.textContent);
    const extent = [
      readValue("westBoundLongitude"),
      readValue("southBoundLatitude"),
      readValue("eastBoundLongitude"),
      readValue("northBoundLatitude"),
    ];
    if (extent.every(Number.isFinite)) {
      return transformExtent(extent, "EPSG:4326", "EPSG:3857");
    }
  }

  throw new Error("the layer extent could not be read");
};

const readGeometryColumnName = async (layerName: string, signal: AbortSignal): Promise<string> => {
  const url = new URL(TANTALIS_WFS_URL);
  url.searchParams.set("service", "WFS");
  url.searchParams.set("version", "2.0.0");
  url.searchParams.set("request", "DescribeFeatureType");
  url.searchParams.set("typeNames", layerName);

  const response = await fetch(url.toString(), { signal });
  if (!response.ok) {
    throw new Error(`the layer description returned status ${response.status}`);
  }

  const xml = new DOMParser().parseFromString(await response.text(), "application/xml");
  if (xml.querySelector("parsererror")) {
    throw new Error("the layer description was not valid XML");
  }

  const geometryElement = Array.from(xml.getElementsByTagNameNS("*", "element")).find((element) =>
    /^[^:]+:.*PropertyType$/i.test(element.getAttribute("type") ?? "")
  );
  const geometryName = geometryElement?.getAttribute("name");
  if (!geometryName || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(geometryName)) {
    throw new Error("the layer geometry column could not be identified");
  }
  return geometryName;
};

const parseLayerDescriptions = (xmlText: string): globalThis.Map<string, string> => {
  const xml = new DOMParser().parseFromString(xmlText, "application/xml");
  if (xml.querySelector("parsererror")) {
    throw new Error("the WMS capabilities were not valid XML");
  }

  const descriptions = new globalThis.Map<string, string>();
  Array.from(xml.getElementsByTagNameNS("*", "Layer")).forEach((layer) => {
    const name = Array.from(layer.children).find((child) => child.localName === "Name")?.textContent?.trim();
    const abstract = Array.from(layer.children).find((child) => child.localName === "Abstract")?.textContent?.trim();
    if (name && abstract) {
      descriptions.set(name, abstract);
    }
  });
  return descriptions;
};

// Named hooks keep external OpenLayers and DOM synchronization in focused lifecycle boundaries.
const useLayerPanelHeight = (
  openMapPanel: "basemap" | "layers" | null,
  panelRef: RefObject<HTMLDivElement | null>,
  frameRef: RefObject<HTMLDivElement | null>,
  controlsRef: RefObject<HTMLDivElement | null>,
  setMaxHeight: (height: number) => void
): void => {
  useEffect(() => {
    // Change: isolated the panel-size synchronization in a named effect hook.
    if (openMapPanel !== "layers") return;

    const panel = panelRef.current;
    const frame = frameRef.current;
    const controls = controlsRef.current;
    if (!panel || !frame || !controls) return;

    let observedFooter: HTMLElement | null = null;
    let resizeObserver: ResizeObserver | undefined;
    const updateLayerPanelHeight = (): void => {
      const footer = document.querySelector<HTMLElement>(".bcgov-page-footer");
      const panelTop = panel.getBoundingClientRect().top;
      const availableBottom = footer?.getBoundingClientRect().top ?? window.innerHeight;
      const availableHeight = Math.max(0, availableBottom - panelTop - 8);
      setMaxHeight(Math.min(380, availableHeight));
      if (footer !== observedFooter) {
        if (observedFooter) resizeObserver?.unobserve(observedFooter);
        observedFooter = footer;
        if (footer) resizeObserver?.observe(footer);
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
      resizeObserver?.disconnect();
      mutationObserver.disconnect();
      window.removeEventListener("resize", updateLayerPanelHeight);
    };
  }, [openMapPanel, panelRef, frameRef, controlsRef, setMaxHeight]);
};

const useSyncTantalisLayers = (
  visibleLayers: Record<string, boolean>,
  selectedStyles: Record<string, string>,
  layerRefs: RefObject<Record<string, TileLayer<TileWMS>>>,
  toggleRefs: RefObject<Record<string, HTMLInputElement | null>>
): void => {
  useEffect(() => {
    // Change: visibility and WMS style synchronization is now a named external-system hook.
    Object.entries(visibleLayers).forEach(([name, isVisible]) => {
      layerRefs.current[name]?.setVisible(isVisible);
    });
    Object.entries(layerRefs.current).forEach(([name, layer]) => {
      layer.getSource()?.updateParams({ STYLES: selectedStyles[name] ?? "" });
    });
    MAP_LAYER_GROUPS.forEach((group) => {
      const enabledCount = group.layers.filter((layer) => visibleLayers[layer.name]).length;
      const groupToggle = toggleRefs.current[group.id];
      if (groupToggle) {
        groupToggle.indeterminate = enabledCount > 0 && enabledCount < group.layers.length;
      }
    });
  }, [visibleLayers, selectedStyles, layerRefs, toggleRefs]);
};

const useSyncMapView = (
  mapRef: RefObject<Map | null>,
  center: [number, number],
  zoom: number
): void => {
  useEffect(() => {
    // Change: OpenLayers view synchronization is isolated from component rendering.
    mapRef.current?.getView().animate({ center: fromLonLat(center), zoom, duration: 400 });
  }, [center, zoom, mapRef]);
};

const useSyncBasemap = (
  mapRef: RefObject<Map | null>,
  selectedBasemap: BasemapId
): void => {
  useEffect(() => {
    // Change: swapping external tile sources is explicit and independently testable.
    const baseLayer = mapRef.current?.getLayers().item(0);
    if (!(baseLayer instanceof TileLayer)) return;
    const url = selectedBasemap === "street" ? STREET_URL : SATELLITE_URL;
    baseLayer.setSource(createBasemapSource(url));
  }, [selectedBasemap, mapRef]);
};

const useMapResize = (
  mapContainerRef: RefObject<HTMLDivElement | null>,
  mapRef: RefObject<Map | null>
): void => {
  useEffect(() => {
    // Change: ResizeObserver lifecycle is named and no component-render logic is mixed into it.
    const mapContainer = mapContainerRef.current;
    if (!mapContainer) return;
    const resizeObserver = new ResizeObserver(() => mapRef.current?.updateSize());
    resizeObserver.observe(mapContainer);
    return () => resizeObserver.disconnect();
  }, [mapContainerRef, mapRef]);
};

const useSyncPreviewStyle = (
  previewLayerRef: RefObject<VectorLayer<VectorSource> | null>,
  previewHue: number,
  previewOpacity: number
): void => {
  useEffect(() => {
    // Change: restyling an external OpenLayers layer is kept in a named synchronization hook.
    previewLayerRef.current?.setStyle(buildPreviewStyle(previewHue, previewOpacity));
  }, [previewHue, previewOpacity, previewLayerRef]);
};

// The map component. It creates the OpenLayers map and handles everything the map does.
const OLMap: FC<OLMapProps> = ({
  // If LandingPage doesn't send a center or zoom, use the defaults.
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  onPolygonClick,
  tantalisPreview,
  onShapeLoaded,
  criticalConflictsRequest,
  isCriticalConflictsOpen,
  onCloseCriticalConflicts,
}) => {
  // The <div> the map is drawn inside.
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapFrameRef = useRef<HTMLDivElement | null>(null);
  const mapControlsRef = useRef<HTMLDivElement | null>(null);
  const layerPanelRef = useRef<HTMLDivElement | null>(null);
  // The OpenLayers map, so every part of this file can reach it.
  const mapRef = useRef<Map | null>(null);
  // The layer showing the current Tantalis preview shape, so the sliders can restyle it.
  const previewLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  // References let the layer panel update individual OpenLayers WMS layers.
  const tantalisLayerRefs = useRef<Record<string, TileLayer<TileWMS>>>({});
  const layerGroupToggleRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const queryHighlightLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const queryAbortRef = useRef<AbortController | null>(null);
  const criticalConflictLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const criticalConflictsAbortRef = useRef<AbortController | null>(null);
  const layerZoomAbortRef = useRef<AbortController | null>(null);
  const criticalConflictHoverRef = useRef<object | null>(null);
  const criticalConflictPinnedRef = useRef<object | null>(null);
  const criticalConflictDescriptionsRef = useRef<Promise<globalThis.Map<string, string>> | null>(null);

  // Which basemap is selected. Starts on satellite.
  const [selectedBasemap, setSelectedBasemap] = useState<BasemapId>("satellite");
  // One active popup keeps map tools from stacking on top of each other.
  const [openMapPanel, setOpenMapPanel] = useState<"basemap" | "layers" | null>(null);
  const [layerPanelMaxHeight, setLayerPanelMaxHeight] = useState<number>();
  // The active layer is the most recently enabled layer and receives symbology/query actions.
  const [activeTantalisLayer, setActiveTantalisLayer] = useState<string>(TANTALIS_LAYER);
  const [openLayerQueries, setOpenLayerQueries] = useState<Record<string, boolean>>({});
  const [openLayerSymbology, setOpenLayerSymbology] = useState<Record<string, boolean>>({});
  const [openLayerActionMenu, setOpenLayerActionMenu] = useState<string | null>(null);
  const [selectedTantalisStyles, setSelectedTantalisStyles] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      MAP_LAYER_GROUPS.flatMap((group) => group.layers.map((layer) => [layer.name, layer.styles[0]?.name ?? ""]))
    )
  );
  const [selectedQueryAttributes, setSelectedQueryAttributes] = useState<Record<string, string>>({});
  const [selectedQueryOperators, setSelectedQueryOperators] = useState<Record<string, QueryOperator>>({});
  const [queryAttributeValues, setQueryAttributeValues] = useState<Record<string, string>>({});
  const [queryResults, setQueryResults] = useState<TantalisQueryResult[]>([]);
  const [queryStatus, setQueryStatus] = useState<string>("");
  const [isQuerying, setIsQuerying] = useState<boolean>(false);
  const [zoomingObjectId, setZoomingObjectId] = useState<string | null>(null);
  const [zoomingLayerName, setZoomingLayerName] = useState<string | null>(null);
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
  const [criticalConflictLayers, setCriticalConflictLayers] = useState<CriticalConflictLayer[]>([]);
  const [criticalConflictErrors, setCriticalConflictErrors] = useState<CriticalConflictError[]>([]);
  const [criticalConflictsChecking, setCriticalConflictsChecking] = useState(false);
  const [criticalConflictStatus, setCriticalConflictStatus] = useState("");
  const [hoveredConflictLayerName, setHoveredConflictLayerName] = useState<string | null>(null);
  const [pinnedConflictLayerName, setPinnedConflictLayerName] = useState<string | null>(null);

  const toggleMapPanel = (panel: "basemap" | "layers"): void => {
    setOpenMapPanel((current) => (current === panel ? null : panel));
  };

  const clearCriticalConflicts = useCallback((): void => {
    criticalConflictsAbortRef.current?.abort();
    criticalConflictsAbortRef.current = null;
    const map = mapRef.current;
    const layer = criticalConflictLayerRef.current;
    if (map && layer) {
      map.removeLayer(layer);
      layer.getSource()?.clear();
    }
    criticalConflictHoverRef.current = null;
    criticalConflictPinnedRef.current = null;
    const target = map?.getTargetElement();
    if (target) {
      target.style.cursor = "";
    }
    setCriticalConflictLayers([]);
    setCriticalConflictErrors([]);
    setCriticalConflictsChecking(false);
    setCriticalConflictStatus("");
    setHoveredConflictLayerName(null);
    setPinnedConflictLayerName(null);
  }, []);

  const handleCloseCriticalConflicts = useCallback((): void => {
    clearCriticalConflicts();
    onCloseCriticalConflicts();
  }, [clearCriticalConflicts, onCloseCriticalConflicts]);

  // External DOM observers remain effects because they synchronize OpenLayers UI with browser layout.
  useLayerPanelHeight(
    openMapPanel,
    layerPanelRef,
    mapFrameRef,
    mapControlsRef,
    setLayerPanelMaxHeight
  );

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

    const normalConflictStyle = new Style({
      fill: new Fill({ color: "rgba(220, 38, 38, 0.18)" }),
      stroke: new Stroke({ color: "#dc2626", width: 2 }),
    });
    const highlightedConflictStyle = new Style({
      fill: new Fill({ color: "rgba(220, 38, 38, 0.3)" }),
      stroke: new Stroke({ color: "#b91c1c", width: 4 }),
    });
    const criticalConflictLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) =>
        feature === criticalConflictHoverRef.current || feature === criticalConflictPinnedRef.current
          ? highlightedConflictStyle
          : normalConflictStyle,
      zIndex: 115,
    });
    criticalConflictLayerRef.current = criticalConflictLayer;

    const findCriticalConflict = (pixel: number[]): object | null =>
      map.forEachFeatureAtPixel(
        pixel,
        (feature) => feature,
        { layerFilter: (layer) => layer === criticalConflictLayerRef.current, hitTolerance: 4 }
      ) ?? null;

    const pointerMoveKey = map.on("pointermove", (event) => {
      const feature = event.dragging ? null : findCriticalConflict(event.pixel);
      const target = map.getTargetElement();
      if (target) {
        target.style.cursor = feature ? "pointer" : "";
      }
      if (criticalConflictHoverRef.current !== feature) {
        criticalConflictHoverRef.current = feature;
        criticalConflictLayer.changed();
      }
      const layerName = feature ? (feature as Feature).get("criticalConflictLayerName") : null;
      setHoveredConflictLayerName(typeof layerName === "string" ? layerName : null);
    });
    const conflictClickKey = map.on("click", (event) => {
      const feature = findCriticalConflict(event.pixel);
      criticalConflictPinnedRef.current = feature;
      criticalConflictLayer.changed();
      const layerName = feature ? (feature as Feature).get("criticalConflictLayerName") : null;
      setPinnedConflictLayerName(typeof layerName === "string" ? layerName : null);
    });

    // Add the scale bar in metres/kilometres.
    // The class name matches the existing CSS that positions and styles it.
    map.addControl(new ScaleLine({ className: "map-scale", units: "metric", minWidth: 140 }));

    // Save the map so the rest of the file can use it.
    mapRef.current = map;

    // Clean up when the component is removed from the page.
    return () => {
      queryAbortRef.current?.abort();
      criticalConflictsAbortRef.current?.abort();
      unByKey([pointerMoveKey, conflictClickKey]);
      const target = map.getTargetElement();
      if (target) {
        target.style.cursor = "";
      }
      map.setTarget(undefined);
      mapRef.current = null;
      queryHighlightLayerRef.current = null;
      criticalConflictLayerRef.current = null;
    };
    // The empty list [] means this runs only once. Later center/zoom changes are handled in step 2.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // External OpenLayers state stays synchronized through one named hook.
  useSyncTantalisLayers(
    visibleTantalisLayers,
    selectedTantalisStyles,
    tantalisLayerRefs,
    layerGroupToggleRefs
  );

  // 2. Move the map smoothly when the center or zoom props change.
  useSyncMapView(mapRef, center, zoom);

  // 3. Swap the basemap tiles when the user picks Street or Satellite.
  useSyncBasemap(mapRef, selectedBasemap);

  // 4. Resize the map whenever its container changes size (for example, when the layout shifts).
  useMapResize(mapContainerRef, mapRef);

  // 5. Show the selected Tantalis shape whenever the form requests a preview.
  // The sliders are left out of the list at the bottom, so moving them doesn't repeat the lookup.
  useEffect(() => {
    const map = mapRef.current;
    onShapeLoaded(false);
    clearCriticalConflicts();
    onCloseCriticalConflicts();

    // Stop if the map isn't ready or nothing has been sent yet.
    if (!map || !tantalisPreview) {
      setPreviewStatus("");
      return;
    }

    const previewSource = new VectorSource();
    const previewLayer = new VectorLayer({
      source: previewSource,
      style: buildPreviewStyle(previewHue, previewOpacity),
      zIndex: 120,
    });
    map.addLayer(previewLayer);
    previewLayerRef.current = previewLayer;
    const controller = new AbortController();

    // Remove extra spaces from the start and end of each value.
    const fileNumber = tantalisPreview.fileNumber.trim();
    const dispositionId = tantalisPreview.dispositionId.trim();
    const parcelId = tantalisPreview.parcelId.trim();

    // The two ID fields are compared as numbers in the filter below,
    // so stop here if they contain anything other than digits.
    if (!isDigitsOnly(dispositionId) || !isDigitsOnly(parcelId)) {
      setPreviewStatus("Disposition ID and Parcel ID must contain numbers only.");
      onShapeLoaded(false);
      map.removeLayer(previewLayer);
      if (previewLayerRef.current === previewLayer) {
        previewLayerRef.current = null;
      }
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

    setPreviewStatus("Loading Tantalis shape...");

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
          setPreviewStatus("No Tantalis shape matched all three identifiers. Check the values and try again.");
          onShapeLoaded(false);
          return;
        }

        // Draw the shape.
        previewSource.addFeatures(features);

        // Get the box around the shape so the map can zoom to it.
        // getExtent() can return null (no box), so check it before zooming.
        const extent = previewSource.getExtent();
        if (!extent) {
          setPreviewStatus("The Tantalis shape was found but has no area to zoom to.");
          onShapeLoaded(false);
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
        onShapeLoaded(true);
      })
      .catch((error: unknown) => {
        // A cancelled request is normal when a newer one replaces it, so ignore it.
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        // Anything else is a real problem, so show it on the map.
        const reason = error instanceof Error ? error.message : "unknown error";
        setPreviewStatus(`Could not load the Tantalis shape: ${reason}.`);
        onShapeLoaded(false);
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
  }, [
    tantalisPreview,
    onShapeLoaded,
    clearCriticalConflicts,
    onCloseCriticalConflicts,
  ]);

  useEffect(() => {
    if (!criticalConflictsRequest) {
      clearCriticalConflicts();
      return;
    }

    criticalConflictsAbortRef.current?.abort();
    const controller = new AbortController();
    criticalConflictsAbortRef.current = controller;
    setCriticalConflictsChecking(true);
    setCriticalConflictStatus("");
    setCriticalConflictLayers([]);
    setCriticalConflictErrors([]);
    criticalConflictHoverRef.current = null;
    criticalConflictPinnedRef.current = null;
    setHoveredConflictLayerName(null);
    setPinnedConflictLayerName(null);

    const map = mapRef.current;
    const inputSource = previewLayerRef.current?.getSource();
    const conflictLayer = criticalConflictLayerRef.current;
    const conflictSource = conflictLayer?.getSource();
    const inputFeatures = inputSource?.getFeatures() ?? [];
    const inputWkts = inputFeatures.flatMap((feature) => {
      const geometry = feature.getGeometry();
      return geometry
        ? [new WKT().writeGeometry(geometry.clone().transform("EPSG:3857", "EPSG:4326"))]
        : [];
    });
    const previewExtent = inputSource?.getExtent();

    if (!map || !inputSource || !conflictLayer || !conflictSource || inputWkts.length === 0 || !previewExtent) {
      setCriticalConflictStatus("The selected shape is not available on the map.");
      setCriticalConflictsChecking(false);
      return () => controller.abort();
    }

    conflictSource.clear();
    if (!map.getLayers().getArray().includes(conflictLayer)) {
      map.addLayer(conflictLayer);
    }

    const criticalGroup = MAP_LAYER_GROUPS.find((group) => group.id === "critical-overlaps");
    if (!criticalGroup) {
      setCriticalConflictStatus("Critical conflict layers are not configured.");
      setCriticalConflictsChecking(false);
      return () => controller.abort();
    }

    const getLayerDescriptions = (): Promise<globalThis.Map<string, string>> => {
      if (!criticalConflictDescriptionsRef.current) {
        const url = new URL(TANTALIS_WMS_URL);
        url.searchParams.set("service", "WMS");
        url.searchParams.set("version", "1.3.0");
        url.searchParams.set("request", "GetCapabilities");
        let descriptionRequest: Promise<globalThis.Map<string, string>>;
        descriptionRequest = fetch(url.toString(), { signal: controller.signal })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`WMS capabilities returned status ${response.status}`);
            }
            return response.text();
          })
          .then(parseLayerDescriptions)
          .catch((error: unknown) => {
            if (controller.signal.aborted) {
              if (criticalConflictDescriptionsRef.current === descriptionRequest) {
                criticalConflictDescriptionsRef.current = null;
              }
              throw error;
            }
            return new globalThis.Map<string, string>();
          });
        criticalConflictDescriptionsRef.current = descriptionRequest;
      }
      return criticalConflictDescriptionsRef.current;
    };

    const checkCriticalConflicts = async (): Promise<void> => {
      const checkedLayers = await Promise.all(
        criticalGroup.layers.map(async (layer): Promise<CriticalLayerCheck | null> => {
          try {
            const geometryColumn = await readGeometryColumnName(layer.name, controller.signal);
            const url = new URL(TANTALIS_WFS_URL);
            url.searchParams.set("service", "WFS");
            url.searchParams.set("version", "2.0.0");
            url.searchParams.set("request", "GetFeature");
            url.searchParams.set("typeNames", layer.name);
            url.searchParams.set("outputFormat", "application/json");
            url.searchParams.set("srsName", "EPSG:4326");
            url.searchParams.set(
              "CQL_FILTER",
              inputWkts.map((wkt) => `INTERSECTS(${geometryColumn},${wkt})`).join(" OR ")
            );

            const response = await fetch(url.toString(), { signal: controller.signal });
            if (!response.ok) {
              throw new Error(`the map service returned status ${response.status}`);
            }
            const geoJson: unknown = await response.json();
            if (!isTantalisQueryResponse(geoJson)) {
              throw new Error("the map service returned an unexpected conflict response");
            }
            const features = new GeoJSON().readFeatures(geoJson, {
              dataProjection: "EPSG:4326",
              featureProjection: "EPSG:3857",
            }) as Feature[];
            features.forEach((feature) => feature.set("criticalConflictLayerName", layer.name));
            return { layer, features, status: "success" };
          } catch (error) {
            if (controller.signal.aborted) {
              return null;
            }
            return {
              layer,
              features: [],
              status: "error",
              message: error instanceof Error ? error.message : "unknown error",
            };
          }
        })
      );

      if (controller.signal.aborted) {
        return;
      }

      const overlaps = checkedLayers.filter(
        (result): result is CriticalLayerCheck =>
          result !== null && result.status === "success" && result.features.length > 0
      );
      overlaps.forEach(({ features }) => conflictSource.addFeatures(features));
      if (overlaps.length > 0) {
        setVisibleTantalisLayers((current) => ({
          ...current,
          ...Object.fromEntries(overlaps.map(({ layer }) => [layer.name, true])),
        }));
      }

      let descriptions = new globalThis.Map<string, string>();
      if (overlaps.length > 0) {
        descriptions = await getLayerDescriptions();
      }

      if (controller.signal.aborted) {
        return;
      }

      setCriticalConflictLayers(
        overlaps.map(({ layer }) => ({
          name: layer.name,
          label: layer.label,
          description: descriptions.get(layer.name) ?? "Layer description unavailable.",
        }))
      );
      setCriticalConflictErrors(
        checkedLayers.flatMap((result) =>
          result?.status === "error"
            ? [{
                layerName: result.layer.name,
                layerLabel: result.layer.label,
                message: result.message ?? "unknown error",
              }]
            : []
        )
      );

      const extent = createEmpty();
      extendExtent(extent, previewExtent);
      conflictSource.getFeatures().forEach((feature) => {
        const featureExtent = feature.getGeometry()?.getExtent();
        if (featureExtent) {
          extendExtent(extent, featureExtent);
        }
      });
      map.getView().fit(extent, {
        padding: [30, 30, 30, 30],
        maxZoom: 16,
        duration: 600,
      });
      setCriticalConflictsChecking(false);
    };

    void checkCriticalConflicts().catch((error: unknown) => {
      if (controller.signal.aborted) {
        return;
      }
      setCriticalConflictStatus(`Could not check critical conflicts: ${error instanceof Error ? error.message : "unknown error"}`);
      setCriticalConflictsChecking(false);
    });

    return () => {
      controller.abort();
      if (criticalConflictsAbortRef.current === controller) {
        criticalConflictsAbortRef.current = null;
      }
    };
  }, [criticalConflictsRequest, clearCriticalConflicts]);

  // Search only attribute fields first; the WMS overlay stays hidden unless its checkbox is enabled.
  const searchTantalisLayer = async (
    event: FormEvent<HTMLFormElement>,
    targetLayer: MapLayerDefinition,
    attributeFilter: { attribute: TantalisQueryAttribute; value: string; operator: QueryOperator }
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
    url.searchParams.set(
      "CQL_FILTER",
      `${attributeFilter.attribute.name}${attributeFilter.operator}${value}`
    );
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
      setQueryStatus(`Could not search Tantalis: ${reason}.`);
    } finally {
      if (queryAbortRef.current === controller) {
        queryAbortRef.current = null;
        setIsQuerying(false);
      }
    }
  };

  const zoomToTantalisLayer = async (layer: MapLayerDefinition): Promise<void> => {
    layerZoomAbortRef.current?.abort();
    const controller = new AbortController();
    layerZoomAbortRef.current = controller;
    setZoomingLayerName(layer.name);
    try {
      const extent = await readWmsLayerExtent(layer.name, controller.signal);
      if (!controller.signal.aborted) {
        mapRef.current?.getView().fit(extent, {
          padding: [36, 36, 36, 36],
          maxZoom: 16,
          duration: 600,
        });
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setQueryStatus(
          `Could not zoom to ${layer.label}: ${error instanceof Error ? error.message : "unknown error"}.`
        );
      }
    } finally {
      if (layerZoomAbortRef.current === controller) {
        layerZoomAbortRef.current = null;
        setZoomingLayerName(null);
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
  useSyncPreviewStyle(previewLayerRef, previewHue, previewOpacity);

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

        {/* Loading and error messages for the Tantalis lookup. Only shown when there is a message.
            role="status" lets screen readers announce it. */}
        {previewStatus && (
          <div className="map-preview-status" role="status" aria-live="polite">
            {previewStatus}
          </div>
        )}

        <CriticalConflictsPanel
          layers={criticalConflictLayers}
          errors={criticalConflictErrors}
          isChecking={criticalConflictsChecking}
          isOpen={isCriticalConflictsOpen}
          selectedLayerName={pinnedConflictLayerName ?? hoveredConflictLayerName}
          status={criticalConflictStatus}
          onClose={handleCloseCriticalConflicts}
        />

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
                                    if (!isVisible) {
                                      setOpenLayerActionMenu(null);
                                    }
                                    if (isVisible) {
                                      selectQueryLayer(layer.name);
                                    }
                                  }}
                                />
                                <span className="map-layer-name">{layer.label}</span>
                              </label>
                              {visibleTantalisLayers[layer.name] && (
                                <div className="map-layer-menu">
                                  <button
                                    type="button"
                                    className="map-layer-menu-toggle"
                                    aria-label={`${openLayerActionMenu === layer.name ? "Close" : "Open"} ${layer.label} options`}
                                    aria-haspopup="menu"
                                    aria-expanded={openLayerActionMenu === layer.name}
                                    title={`${layer.label} options`}
                                    onClick={() => {
                                      setOpenLayerActionMenu((current) =>
                                        current === layer.name ? null : layer.name
                                      );
                                    }}
                                  >
                                    <span aria-hidden="true">▾</span>
                                  </button>
                                  {openLayerActionMenu === layer.name && (
                                    <div className="map-layer-menu-options" role="menu" aria-label={`${layer.label} options`}>
                                      <button
                                        type="button"
                                        role="menuitemcheckbox"
                                        aria-checked={Boolean(openLayerQueries[layer.name])}
                                        onClick={() => {
                                          const isOpening = !openLayerQueries[layer.name];
                                          setOpenLayerQueries((current) => ({ ...current, [layer.name]: isOpening }));
                                          setOpenLayerSymbology((current) => ({ ...current, [layer.name]: false }));
                                          setOpenLayerActionMenu(null);
                                          if (isOpening && activeTantalisLayer !== layer.name) {
                                            selectQueryLayer(layer.name);
                                          }
                                        }}
                                      >
                                        Query Layer
                                      </button>
                                      <button
                                        type="button"
                                        role="menuitemcheckbox"
                                        aria-checked={Boolean(openLayerSymbology[layer.name])}
                                        onClick={() => {
                                          const isOpening = !openLayerSymbology[layer.name];
                                          setOpenLayerSymbology((current) => ({
                                            ...current,
                                            [layer.name]: isOpening,
                                          }));
                                          setOpenLayerQueries((current) => ({ ...current, [layer.name]: false }));
                                          setOpenLayerActionMenu(null);
                                        }}
                                      >
                                        Symbology
                                      </button>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                            {visibleTantalisLayers[layer.name] && openLayerSymbology[layer.name] && (
                              <div className="map-layer-symbology-controls">
                                <select
                                  aria-label={`${layer.label} symbology`}
                                  title={`${layer.label} symbology`}
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
                                <button
                                  type="button"
                                  className="map-layer-filter-submit"
                                  aria-label={`Zoom to ${layer.label}`}
                                  title={`Zoom to ${layer.label}`}
                                  disabled={zoomingLayerName !== null}
                                  onClick={() => void zoomToTantalisLayer(layer)}
                                >
                                  {zoomingLayerName === layer.name ? "Loading..." : "Zoom to Layer"}
                                </button>
                              </div>
                            )}
                            {visibleTantalisLayers[layer.name] && openLayerQueries[layer.name] && (
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
                                    operator: selectedQueryOperators[layer.name] ?? "=",
                                  });
                                }}
                              >
                                <label className="map-layer-query-control">
                                  <span>Field</span>
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
                                </label>
                                <label className="map-layer-query-control">
                                  <span>Operator</span>
                                  <select
                                    aria-label={`${layer.label} query operator`}
                                    title={`${layer.label} query operator`}
                                    value={selectedQueryOperators[layer.name] ?? "="}
                                    onChange={(event) => {
                                      const operator = event.currentTarget.value as QueryOperator;
                                      setSelectedQueryOperators((current) => ({
                                        ...current,
                                        [layer.name]: operator,
                                      }));
                                    }}
                                  >
                                    <option value="<">Less than (&lt;)</option>
                                    <option value="<=">Less than or equal to (&lt;=)</option>
                                    <option value="=">Equal to (=)</option>
                                    <option value=">=">Greater than or equal to (&gt;=)</option>
                                    <option value=">">Greater than (&gt;)</option>
                                    <option value="<>">Not equal to (&lt;&gt;)</option>
                                  </select>
                                </label>
                                <label className="map-layer-query-control map-layer-query-control--value">
                                  <span>Value</span>
                                  <input
                                    type={selectedAttribute?.type === "date" ? "date" : "text"}
                                    inputMode={selectedAttribute?.type === "number" ? "numeric" : undefined}
                                    aria-label={`${layer.label} ${selectedAttribute?.label ?? "attribute"} value`}
                                    placeholder={selectedAttribute?.label ?? "Enter a value"}
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
                                </label>
                                <button
                                  type="submit"
                                  className="map-layer-filter-submit map-layer-filter-submit--inline"
                                  aria-label="Search and Zoom"
                                  title="Search and Zoom"
                                  disabled={
                                    !selectedQueryAttributes[layer.name] ||
                                    !queryAttributeValues[layer.name]?.trim() ||
                                    isQuerying
                                  }
                                >
                                  Search and Zoom
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
                            {visibleTantalisLayers[layer.name] &&
                              openLayerQueries[layer.name] &&
                              activeTantalisLayer === layer.name &&
                              queryStatus && (
                              <div className="map-query-status" role="status" aria-live="polite">
                                {queryStatus}
                              </div>
                            )}
                            {visibleTantalisLayers[layer.name] &&
                              openLayerQueries[layer.name] &&
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
