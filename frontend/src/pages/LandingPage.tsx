// Styles for this page's layout (form and map side by side).
import "./LandingPage.scss";

// React tools:
// useState = store a value that redraws the page when it changes.
// useCallback = keep the same copy of a function between redraws, instead of making a new one each time.
import { useCallback, useState } from "react";
// The form (left side of the page).
import ASTForm from "../components/ast-form";
// The map (right side of the page).
import OLMap from "../components/OLMap";

// The three TANTALIS identifiers. All values are kept as text (strings) in the app.
interface TantalisIdentifiers {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

// A shape clicked on the map.
// clickedAt stores the time of the click, so clicking the same shape twice still counts as a new click.
interface MapSelection extends TantalisIdentifiers {
  clickedAt: number;
}

// The landing page. The form and the map can't talk to each other directly,
// so this page holds the shared information and passes it between them:
// ASTForm <-> LandingPage <-> OLMap
const LandingPage = () => {
  // The shape most recently clicked on the map. The form uses it to fill in the three ID fields.
  // Starts as null because nothing has been clicked yet.
  const [mapSelection, setMapSelection] = useState<MapSelection | null>(null);

  // The identifiers sent from the form. The map watches this and runs the TANTALIS lookup when it changes.
  // Starts as null because nothing has been sent yet.
  const [tantalisPreview, setTantalisPreview] = useState<TantalisIdentifiers | null>(null);

  // Runs when a shape is clicked on the map. Saves its identifiers plus the time of the click.
  // useCallback keeps this the same function between redraws, so the map
  // doesn't have to remove and re-add its click listener every time the page redraws.
  const handlePolygonClick = useCallback((selection: TantalisIdentifiers): void => {
    setMapSelection({ ...selection, clickedAt: Date.now() });
  }, []);

  // What appears on the page.
  return (
    <div className="landing-page">
      {/* The form.
          mapSelection = the clicked shape, used to fill in the ID fields.
          onViewTantalis = saves the identifiers when "View shape on map" is clicked.
          setTantalisPreview is passed straight in, because saving the values is all it needs to do. */}
      <ASTForm mapSelection={mapSelection} onViewTantalis={setTantalisPreview} />

      {/* The map.
          onPolygonClick = runs when a shape is clicked.
          tantalisPreview = the identifiers to look up and show. */}
      <OLMap onPolygonClick={handlePolygonClick} tantalisPreview={tantalisPreview} />
    </div>
  );
};

export default LandingPage;
