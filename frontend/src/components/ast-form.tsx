// React tools:
// useEffect = run code when something changes (for example, when a map shape is clicked).
// useRef = keep a direct link to an element on the page (the file picker).
// useState = store a value that redraws the form when it changes.
import { useEffect, useRef, useState } from "react";
// Types only. These add nothing to the final app.
// ChangeEvent = the event from a normal HTML input. FC = "function component".
import type { ChangeEvent, FC } from "react";
// Ready-made form pieces from the BC Government design system.
import { Button, Switch, Select, Radio, RadioGroup, TextField } from "@bcgov/design-system-react-components";
// Styles for this form.
import "./ast-form.scss";

// The three TANTALIS identifiers. All values are kept as text (strings) in the app.
interface TantalisIdentifiers {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

// A shape clicked on the map, passed down from LandingPage.
// clickedAt makes each click count as new, even if the same shape is clicked twice.
interface MapSelection extends TantalisIdentifiers {
  clickedAt: number;
}

// Everything LandingPage passes into this form. The ? means the value is optional.
interface ASTFormProps {
  // The shape most recently clicked on the map, or null if nothing has been clicked.
  mapSelection?: MapSelection | null;
  // Sends the three identifiers up to LandingPage so the map can show the shape.
  // Required, because the "View shape on map" button can't work without it.
  onViewTantalis: (request: TantalisIdentifiers) => void;
}

// Every field in the form and the type of value it holds.
interface FormInputs {
  name: string;
  email: string;
  region: string; // Region id, for example "omineca". Empty = nothing picked.
  source: string; // "1" = TANTALIS, "2" = Upload. Empty = nothing picked.
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
  uploadFile: File | null; // The chosen file, or null if none.
  maps: boolean; // Generate Maps switch (true = on)
  overlaps: boolean; // Export Overlap Results switch (true = on)
}

// Values for the two Source radio buttons.
const SOURCE_TANTALIS = "1";
const SOURCE_UPLOAD = "2";

// Starting values for every field. Also used when the form is cleared.
// Kept outside the component so it isn't rebuilt on every redraw.
const INITIAL_INPUTS: FormInputs = {
  name: "",
  email: "",
  region: "",
  source: "",
  fileNumber: "",
  dispositionId: "",
  parcelId: "",
  uploadFile: null,
  maps: false,
  overlaps: false,
};

// Options for the Region dropdown. id = value stored, label = text shown.
const REGION_ITEMS = [
  { id: "cariboo", label: "Cariboo" },
  { id: "kootenay", label: "Kootenay" },
  { id: "northeast", label: "Northeast" },
  { id: "omineca", label: "Omineca" },
  { id: "skeena", label: "Skeena" },
  { id: "south_coast", label: "South Coast" },
  { id: "thompson_okanagan", label: "Thompson Okanagan" },
  { id: "west_coast", label: "West Coast" },
];

// The AST form component.
const ASTForm: FC<ASTFormProps> = ({ mapSelection, onViewTantalis }) => {
  // All current field values, stored together in one object.
  const [inputs, setInputs] = useState<FormInputs>(INITIAL_INPUTS);
  // Message shown under the "View shape on map" button. Empty = no message.
  const [previewMessage, setPreviewMessage] = useState<string>("");
  // Direct link to the file picker, so it can be emptied.
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Updates one field and keeps all the others.
  // K is the field name. FormInputs[K] makes sure the value is the right type for that field
  // (for example, text for "name" and true/false for "maps").
  const updateField = <K extends keyof FormInputs>(field: K, value: FormInputs[K]): void => {
    setInputs((values) => ({ ...values, [field]: value }));
  };

  // Empties the file picker. The browser keeps its own copy of the chosen file,
  // so this has to be cleared separately from our form values.
  const clearFileInput = (): void => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Saves the file the user picked. If they cancel, saves null.
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    updateField("uploadFile", event.target.files?.[0] ?? null);
  };

  // Removes the chosen file.
  const handleRemoveFile = (): void => {
    updateField("uploadFile", null);
    clearFileInput();
  };

  // Resets the whole form back to its starting values.
  const handleClearAll = (): void => {
    setInputs(INITIAL_INPUTS);
    setPreviewMessage("");
    clearFileInput();
  };

  // When a shape is clicked on the map, put each identifier in its matching field
  // and switch Source to TANTALIS so those fields are visible.
  useEffect(() => {
    // Nothing clicked yet.
    if (!mapSelection) {
      return;
    }

    setInputs((values) => ({
      ...values,
      source: SOURCE_TANTALIS,
      fileNumber: mapSelection.fileNumber,
      dispositionId: mapSelection.dispositionId,
      parcelId: mapSelection.parcelId,
    }));
    setPreviewMessage("");
  }, [mapSelection]); // Runs every time a new shape is clicked.

  // Runs when "View shape on map" is clicked.
  // Sends the typed identifiers up to LandingPage, which passes them to the map.
  const handleViewTantalisInMap = (): void => {
    // Remove extra spaces from the start and end of each value.
    const fileNumber = inputs.fileNumber.trim();
    const dispositionId = inputs.dispositionId.trim();
    const parcelId = inputs.parcelId.trim();

    // All three are needed for the lookup. Show a message if any are empty.
    if (!fileNumber || !dispositionId || !parcelId) {
      setPreviewMessage("Enter a File Number, Disposition ID and Parcel ID first.");
      return;
    }

    // Clear any old message and send the values up.
    setPreviewMessage("");
    onViewTantalis({ fileNumber, dispositionId, parcelId });
  };

  // What appears on the page.
  return (
    <div className="form-container">
      {/* Name field */}
      <div className="full-width-field">
        <TextField
          label="Name"
          name="name"
          value={inputs.name}
          onChange={(value) => updateField("name", value)}
        />
      </div>

      {/* Email field. type="email" gives an email keyboard on phones. */}
      <div className="full-width-field">
        <TextField
          label="Email"
          name="email"
          type="email"
          value={inputs.email}
          onChange={(value) => updateField("email", value)}
        />
      </div>

      {/* Region dropdown. selectedKey is null when nothing is picked, so the placeholder shows. */}
      <Select
        label="Region"
        name="region"
        items={REGION_ITEMS}
        selectionMode="single"
        size="medium"
        selectedKey={inputs.region || null}
        onSelectionChange={(key) => updateField("region", key == null ? "" : String(key))}
      />

      <div className="source-container">
        {/* Source: choose a TANTALIS lookup or an uploaded file. */}
        <RadioGroup
          label="Source"
          orientation="horizontal"
          name="source"
          value={inputs.source}
          onChange={(value) => updateField("source", value)}
        >
          <Radio value={SOURCE_TANTALIS}>TANTALIS</Radio>
          <Radio value={SOURCE_UPLOAD}>Upload</Radio>
        </RadioGroup>

        {/* TANTALIS section. Always on the page, but only opens (with a CSS animation)
            when TANTALIS is picked. The "expanded" class is what opens it. */}
        <div className={`source-details ${inputs.source === SOURCE_TANTALIS ? "expanded" : ""}`}>
          <div className="source-details-inner tantalis-inputs">
            <hr />
            {/* The three TANTALIS identifiers. Also filled in automatically when a map shape is clicked. */}
            <TextField
              label="File Number"
              name="fileNumber"
              value={inputs.fileNumber}
              onChange={(value) => updateField("fileNumber", value)}
            />
            <TextField
              label="Disposition ID"
              name="dispositionId"
              value={inputs.dispositionId}
              onChange={(value) => updateField("dispositionId", value)}
            />
            <TextField
              label="Parcel ID"
              name="parcelId"
              value={inputs.parcelId}
              onChange={(value) => updateField("parcelId", value)}
            />

            <div className="tantalis-preview-row">
              {/* Sends the three identifiers to the map. type="button" so it never submits the form. */}
              <button type="button" className="tantalis-preview-link" onClick={handleViewTantalisInMap}>
                View shape on map
              </button>

              {/* Message under the button. Only shown when there is one.
                  role="status" lets screen readers announce it. */}
              {previewMessage && (
                <p className="tantalis-preview-message" role="status" aria-live="polite">
                  {previewMessage}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Upload section. Only opens when Upload is picked. */}
        <div className={`source-details ${inputs.source === SOURCE_UPLOAD ? "expanded" : ""}`}>
          <div className="source-details-inner upload-inputs">
            <hr />
            <p>Select File:</p>
            <div className="upload-input-row">
              {/* File picker. accept limits it to these spatial file types. */}
              <input
                type="file"
                accept=".geojson,.json,.kml,.shp"
                ref={fileInputRef}
                onChange={handleFileChange}
              />
              {/* Name of the chosen file. Only shown once a file is picked. */}
              {inputs.uploadFile && <span className="upload-file-name">{inputs.uploadFile.name}</span>}
            </div>

            {/* Remove button. Only shown once a file is picked. */}
            {inputs.uploadFile && (
              <button type="button" onClick={handleRemoveFile}>
                Remove file
              </button>
            )}
          </div>
        </div>
      </div>

      {/* On/off switches for the output options. */}
      <div className="switch-container">
        <Switch
          labelPosition="right"
          name="maps"
          isSelected={inputs.maps}
          onChange={(value) => updateField("maps", value)}
        >
          Generate Maps
        </Switch>

        <Switch
          labelPosition="right"
          name="overlaps"
          isSelected={inputs.overlaps}
          onChange={(value) => updateField("overlaps", value)}
        >
          Export Overlap Results
        </Switch>
      </div>

      <div className="button-container">
        {/* Submit button. Note: there is no <form> around these fields and no submit
            function yet, so this button doesn't do anything at the moment. */}
        <Button variant="primary" type="submit">
          Submit
        </Button>
        {/* Clear button. type="button" so it never submits.
            onPress is the design system's version of onClick. */}
        <Button variant="secondary" type="button" onPress={handleClearAll}>
          Clear Form
        </Button>
      </div>
    </div>
  );
};

export default ASTForm;
