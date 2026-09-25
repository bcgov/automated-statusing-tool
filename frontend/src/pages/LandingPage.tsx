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

// LandingPage is the main AST workflow page.
// It owns the shared state between the form and the map so a user can:
// 1. enter TANTALIS identifiers in the form,
// 2. click a parcel on the map, and
// 3. view the matching parcel highlight in the map preview area.
const LandingPage = () => {
  // Tracks the parcel selected by clicking on the map so the form can reuse that parcel ID in the matching field.
  const [mapSelection, setMapSelection] = useState<MapSelection | null>(null);
  // Stores the TANTALIS preview request created from the form. The map reads this value and queries the public parcel layer.
  const [tantalisPreview, setTantalisPreview] = useState<TantalisPreviewRequest | null>(null);

  // When the user clicks a parcel on the map, store the selected disposition ID and a timestamp.
  // The timestamp forces React to treat repeated clicks as a distinct state update.
  const handlePolygonClick = (dispositionId: string) => {
    setMapSelection({ dispositionId, clickedAt: Date.now() });
  };

  // Receives the submitted TANTALIS identifiers from the form and pushes them to the map preview layer.
  const handleViewTantalis = (request: TantalisPreviewRequest) => {
    setTantalisPreview(request);
  };

  return (
    <div className="landing-page">
      {/* The form captures the user input and triggers the map preview for a specific TANTALIS parcel. */}
      <ASTForm mapSelection={mapSelection} onViewTantalis={handleViewTantalis} />
      {/* The map displays the BC basemap, the TANTALIS parcel preview, and the parcel selection behaviour. */}
      <OLMap
        onPolygonClick={handlePolygonClick}
        tantalisPreview={tantalisPreview}
      />
    </div>
  );
};

export default LandingPage;