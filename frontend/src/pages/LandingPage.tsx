import "./LandingPage.scss";

import { useState } from "react";
import ASTForm from "../components/ast-form";
import OLMap from "../components/OLMap";

interface MapSelection {
  dispositionId: string;
  clickedAt: number; // forces a "new" value even on repeat clicks
}

interface TantalisPreviewRequest {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

const LandingPage = () => {
  // updated week of sept 21: track the parcel selected from the map so the form can prefill the matching identifier.
  const [mapSelection, setMapSelection] = useState<MapSelection | null>(null);
  // updated week of sept 21: hold the TANTALIS identifiers entered in the form so the map can query and highlight the parcel when it changes.
  const [tantalisPreview, setTantalisPreview] = useState<TantalisPreviewRequest | null>(null);

  const handlePolygonClick = (dispositionId: string) => {
    setMapSelection({ dispositionId, clickedAt: Date.now() });
  };

  // Store the preview request from the form so the map can fetch and highlight the matching TANTALIS parcel.
  const handleViewTantalis = (request: TantalisPreviewRequest) => {
    setTantalisPreview(request);
  };

  return (
    <div className="landing-page">
      <ASTForm mapSelection={mapSelection} onViewTantalis={handleViewTantalis} />
      <OLMap
        onPolygonClick={handlePolygonClick}
        tantalisPreview={tantalisPreview}
      />
    </div>
  );
};

export default LandingPage;