import React, { useEffect, useRef, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import { OSM } from "ol/source";
import Feature from "ol/Feature";
import Polygon from "ol/geom/Polygon";
import { Style, Fill, Stroke } from "ol/style";
import { fromLonLat } from "ol/proj";
import ScaleLine from "ol/control/ScaleLine";
import type MapBrowserEvent from "ol/MapBrowserEvent";

import "ol/ol.css";

type BasemapId = "osm" | "satellite";

interface OLMapProps {
  center?: [number, number];
  zoom?: number;
  basemap?: BasemapId;
  refreshTrigger?: number;
  /** Called with a feature's `dispositionId` when a demo polygon is clicked. */
  onPolygonClick?: (dispositionId: string) => void;
}

// Centralized basemap source factory — add new basemaps here only.
const BASEMAP_SOURCES: Record<BasemapId, () => OSM | XYZ> = {
  osm: () => new OSM(),
  satellite: () =>
    new XYZ({
      url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attributions: "Tiles © Esri",
    }),
};

// Demo polygon roughly centered on the default view (near Victoria, BC).
// Swap this for real geometry/attributes once you're pulling from a layer.
function buildDemoPolygonLayer(): VectorLayer<VectorSource> {
  const ring = [
    [-123.42, 48.42],
    [-123.32, 48.42],
    [-123.32, 48.46],
    [-123.42, 48.46],
    [-123.42, 48.42],
  ].map((coord) => fromLonLat(coord));

  const feature = new Feature({
    geometry: new Polygon([ring]),
  });
  feature.set("dispositionId", "DEMO-1234");

  const source = new VectorSource({ features: [feature] });

  return new VectorLayer({
    source,
    style: new Style({
      fill: new Fill({ color: "rgba(47, 216, 255, 0.25)" }),
      stroke: new Stroke({ color: "#2fd8ff", width: 2 }),
    }),
  });
}

// Hoisted so the default is a stable reference across renders — an
// inline array literal as a default value gets recreated on every
// render, which breaks the [center, zoom] effect below (it would
// see a "changed" center every time OLMap re-renders and animate
// the view back to this default, even when nothing actually moved).
const DEFAULT_CENTER: [number, number] = [-123.3656, 48.4284];
const DEFAULT_ZOOM = 6;

const OLMap: React.FC<OLMapProps> = ({
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  basemap = "osm",
  refreshTrigger = 0,
  onPolygonClick,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);
  const demoLayerRef = useRef<VectorLayer<VectorSource> | null>(null);

  const fitMapToExtent = useCallback(
    (extent: number[], options?: { maxZoom?: number; duration?: number }) => {
      if (!mapInstanceRef.current || !extent || extent[0] === Infinity) return;
      mapInstanceRef.current.getView().fit(extent, {
        maxZoom: options?.maxZoom ?? 14,
        duration: options?.duration ?? 1000,
      });
    },
    []
  );

  // Initialize the map once on mount.
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const demoLayer = buildDemoPolygonLayer();
    demoLayerRef.current = demoLayer;

    const initialMap = new Map({
      target: mapContainerRef.current,
      layers: [
        new TileLayer({ source: BASEMAP_SOURCES[basemap]() }),
        demoLayer,
      ],
      view: new View({ center: fromLonLat(center), zoom }),
    });
    initialMap.addControl(new ScaleLine());
    mapInstanceRef.current = initialMap;

    return () => {
      initialMap.setTarget(undefined);
      mapInstanceRef.current = null;
      demoLayerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the map sized correctly if its container is resized, revealed
  // from a hidden tab/modal, or the layout otherwise shifts after mount.
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      mapInstanceRef.current?.updateSize();
    });
    resizeObserver.observe(mapContainerRef.current);

    return () => resizeObserver.disconnect();
  }, []);

  // Swap the basemap source when the `basemap` prop changes.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    const baseLayer = map.getLayers().item(0) as TileLayer<OSM | XYZ> | undefined;
    const buildSource = BASEMAP_SOURCES[basemap];
    if (!baseLayer || !buildSource) return;

    baseLayer.setSource(buildSource());
  }, [basemap]);

  // Recenter/rezoom the view when those props change (skips the very
  // first render since the initial view already reflects them).
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    mapInstanceRef.current?.getView().animate({
      center: fromLonLat(center),
      zoom,
      duration: 500,
    });
  }, [center, zoom]);

  // Placeholder hook point: consumers can trigger a data refresh (e.g.
  // re-fetching a vector layer) by bumping refreshTrigger.
  useEffect(() => {
    if (!mapInstanceRef.current || refreshTrigger === 0) return;
    // Wire up actual refresh logic here (e.g. reloading a vector source).
  }, [refreshTrigger]);

  // Click handling: hit-test features at the click pixel and, for any
  // feature carrying a `dispositionId`, call back up to the parent.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !onPolygonClick) return;

    const handleClick = (evt: MapBrowserEvent) => {
      map.forEachFeatureAtPixel(evt.pixel, (feature) => {
        const dispositionId = feature.get("dispositionId");
        if (typeof dispositionId === "string") {
          onPolygonClick(dispositionId);
          return true; // stop after the first hit
        }
        return false;
      });
    };

    map.on("click", handleClick);
    return () => {
      map.un("click", handleClick);
    };
  }, [onPolygonClick]);

  return <div ref={mapContainerRef} className="map-container" />;
};

export default OLMap;