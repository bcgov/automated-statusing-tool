import "./LandingPage.scss";

import { useState } from "react";
import ASTForm from "../components/ast-form";
import OLMap from "../components/OLMap";

interface MapSelection {
  dispositionId: string;
  clickedAt: number; // forces a "new" value even on repeat clicks
}

const LandingPage = () => {
  const [mapSelection, setMapSelection] = useState<MapSelection | null>(null);

  const handlePolygonClick = (dispositionId: string) => {
    setMapSelection({ dispositionId, clickedAt: Date.now() });
  };

  return (
    <div className="landing-page">
      <ASTForm mapSelection={mapSelection} />
      <OLMap onPolygonClick={handlePolygonClick} />
    </div>
  );
};

export default LandingPage;