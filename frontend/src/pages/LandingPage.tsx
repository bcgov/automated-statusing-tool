// Styles for this page's layout (form and map side by side).
import "./LandingPage.scss";

// React tools:
// useState = store a value that redraws the page when it changes.
// useCallback = keep the same copy of a function between redraws, instead of making a new one each time.
import { useCallback, useState } from "react";
// The form (left side of the page).
import ASTForm, { INITIAL_INPUTS, type FormInputs } from "../components/ast-form";
// The map (right side of the page).
import OLMap from "../components/OLMap";
import type { CriticalConflictsRequest, TantalisIdentifiers } from "../types/tantalis";

// The landing page. The form and the map can't talk to each other directly,
// so this page holds the shared information and passes it between them:
// ASTForm <-> LandingPage <-> OLMap
const LandingPage = () => {
  // Shared form values: a map click updates these immediately through the event handler,
  // so ASTForm does not need an effect to synchronize a selection prop after rendering.
  const [formInputs, setFormInputs] = useState<FormInputs>(INITIAL_INPUTS);
  const [isShapePreviewEnabled, setIsShapePreviewEnabled] = useState(false);
  const [previewMessage, setPreviewMessage] = useState("");

  // The identifiers sent from the form. The map watches this and runs the Tantalis lookup when it changes.
  // Starts as null because nothing has been sent yet.
  const [tantalisPreview, setTantalisPreview] = useState<TantalisIdentifiers | null>(null);
  const [shapeLoaded, setShapeLoaded] = useState(false);
  const [criticalConflictsRequest, setCriticalConflictsRequest] = useState<CriticalConflictsRequest | null>(null);
  const [isCriticalConflictsOpen, setIsCriticalConflictsOpen] = useState(false);

  // Runs when a shape is clicked on the map. Saves its identifiers plus the time of the click.
  // useCallback keeps this the same function between redraws, so the map
  // doesn't have to remove and re-add its click listener every time the page redraws.
  const handlePolygonClick = useCallback((selection: TantalisIdentifiers): void => {
    setFormInputs((values) => ({
      ...values,
      source: "1",
      fileNumber: selection.fileNumber,
      dispositionId: selection.dispositionId,
      parcelId: selection.parcelId,
    }));
    // Change: clear this event-owned UI state directly instead of syncing it in a useEffect.
    setPreviewMessage("");
  }, []);

  const handlePreviewCriticalConflicts = useCallback((): void => {
    setCriticalConflictsRequest({ clickedAt: Date.now() });
    setIsCriticalConflictsOpen(true);
  }, []);

  const handleCloseCriticalConflicts = useCallback((): void => {
    setCriticalConflictsRequest(null);
    setIsCriticalConflictsOpen(false);
  }, []);

  // What appears on the page.
  return (
    <div className="landing-page">
      {/* The form.
          mapSelection = the clicked shape, used to fill in the ID fields.
          onViewTantalis = saves the identifiers when "View shape on map" is clicked.
          setTantalisPreview is passed straight in, because saving the values is all it needs to do. */}
      <ASTForm
        inputs={formInputs}
        onInputsChange={setFormInputs}
        isShapePreviewEnabled={isShapePreviewEnabled}
        onShapePreviewEnabledChange={setIsShapePreviewEnabled}
        previewMessage={previewMessage}
        onPreviewMessageChange={setPreviewMessage}
        onViewTantalis={setTantalisPreview}
        isShapeLoaded={shapeLoaded}
        isCriticalConflictsOpen={isCriticalConflictsOpen}
        onPreviewCriticalConflicts={handlePreviewCriticalConflicts}
        onClearCriticalConflicts={handleCloseCriticalConflicts}
      />

      {/* The map.
          onPolygonClick = runs when a shape is clicked.
          tantalisPreview = the identifiers to look up and show. */}
      <OLMap
        onPolygonClick={handlePolygonClick}
        tantalisPreview={tantalisPreview}
        onShapeLoaded={setShapeLoaded}
        criticalConflictsRequest={criticalConflictsRequest}
        isCriticalConflictsOpen={isCriticalConflictsOpen}
        onCloseCriticalConflicts={handleCloseCriticalConflicts}
      />
    </div>
  );
};

export default LandingPage;
