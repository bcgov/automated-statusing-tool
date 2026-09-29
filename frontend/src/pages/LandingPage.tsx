import "./LandingPage.scss";

import { useState } from "react"; //react hook
import ASTForm from "../components/ast-form"; //form
import OLMap from "../components/OLMap"; //ol map component

interface MapSelection {
  dispositionId: string;
  clickedAt: number; // forces a "new" value even on repeat clicks on the same parcel
}

interface TantalisPreviewRequest {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}
//Required info for querying Tantalis for a parcel preview. Form <-> LandingPage <-> ol map so it can show the matching parcel

const LandingPage = () => {
  // track the parcel selected from the map so the form can prefill the matching identifier
  const [mapSelection, setMapSelection] = useState<MapSelection | null>(null);
  // hold the Tantalis identifiers entered in the form so the map can query and show the matching parcel when it changes
  const [tantalisPreview, setTantalisPreview] = useState<TantalisPreviewRequest | null>(null);

  const handlePolygonClick = (dispositionId: string) => {
    setMapSelection({ dispositionId, clickedAt: Date.now() });
  };

  // Store the preview request from the form so the map can show Tantalis parcel
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