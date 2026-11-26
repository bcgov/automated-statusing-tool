// React tools:
// useRef = keep a direct link to an element on the page (the file picker).
// useState = store local UI values that redraw the form when they change.
import { useRef, useState } from "react";
// Types only. These add nothing to the final app.
// ChangeEvent = the event from a normal HTML input. FC = "function component".
import type { ChangeEvent, FC } from "react";
// Ready-made form pieces from the BC Government design system.
import { Button, Switch, Select, Radio, RadioGroup } from "@bcgov/design-system-react-components";
import type { TantalisIdentifiers } from "../types/tantalis";

// TEMP Test Results from JSON file
import {loadJSON} from "../test/read-jsonfile";
import resultsUrl from '../test/ast_demo_results_20261124.json?url';
import { ResultsWindow } from "./results-display";
import type { JobPayload } from "../types/results";

// Styles for this form.
import "./ast-form.scss";

// Everything LandingPage passes into this form. The ? means the value is optional.
interface ASTFormProps {
  // Shared form values owned by LandingPage.
  inputs: FormInputs;
  onInputsChange: (updater: (values: FormInputs) => FormInputs) => void;
  isShapePreviewEnabled: boolean;
  onShapePreviewEnabledChange: (isEnabled: boolean) => void;
  previewMessage: string;
  onPreviewMessageChange: (message: string) => void;
  // Sends the three identifiers up to LandingPage so the map can show the shape.
  // Required, because the "View shape on map" button can't work without it.
  onViewTantalis: (request: TantalisIdentifiers | null) => void;
  isShapeLoaded: boolean;
  isCriticalConflictsOpen: boolean;
  onPreviewCriticalConflicts: () => void;
  onClearCriticalConflicts: () => void;
}

// Every field in the form and the type of value it holds.
export interface FormInputs {
  name: string;
  email: string;
  region: string; // Region id, for example "omineca". Empty = nothing picked.
  source: string; // "1" = Tantalis, "2" = Upload. Empty = nothing picked.
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
  uploadFiles: File[];
  maps: boolean; // Generate Maps by default; false opts out
  overlaps: boolean; // Export results by default; false opts out
}

// Values for the two Source radio buttons.
const SOURCE_TANTALIS = "1";
const SOURCE_UPLOAD = "2";

// Starting values for every field. Also used when the form is cleared.
// Kept outside the component so it isn't rebuilt on every redraw.
export const INITIAL_INPUTS: FormInputs = {
  name: "",
  email: "",
  region: "",
  source: "",
  fileNumber: "",
  dispositionId: "",
  parcelId: "",
  uploadFiles: [],
  maps: true,
  overlaps: true,
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
const ASTForm: FC<ASTFormProps> = ({
  inputs,
  onInputsChange,
  isShapePreviewEnabled,
  onShapePreviewEnabledChange,
  previewMessage,
  onPreviewMessageChange,
  onViewTantalis,
  onClearCriticalConflicts,
}) => {
  const [selectedUploadPath, setSelectedUploadPath] = useState("");
  // Direct link to the file picker, so it can be reset.
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Results
  const [jobResults, setJobResults] = useState<JobPayload[]>([]);
  const [submitError, setSubmitError] = useState("");

  // Updates one field and keeps all the others.
  // K is the field name. FormInputs[K] makes sure the value is the right type for that field
  // (for example, text for "name" and true/false for "maps").
  const updateField = <K extends keyof FormInputs>(field: K, value: FormInputs[K]): void => {
    onInputsChange((values) => ({ ...values, [field]: value }));
  };

  // Empties the file picker. The browser keeps its own copy of the chosen file,
  // so this has to be cleared separately from our form values.
  const clearFileInput = (): void => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Saves the selected spatial file.
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const files = Array.from(event.target.files ?? []).slice(0, 1);
    updateField("uploadFiles", files);
    const selectedPath = files[0]?.name ?? "";
    setSelectedUploadPath(selectedPath);
  };

  // Removes the chosen file.
  const handleRemoveFile = (): void => {
    updateField("uploadFiles", []);
    setSelectedUploadPath("");
    clearFileInput();
  };

  // Resets the whole form back to its starting values.
  const handleClearAll = (): void => {
    onInputsChange(() => INITIAL_INPUTS);
    setSelectedUploadPath("");
    onShapePreviewEnabledChange(false);
    onPreviewMessageChange("");
    clearFileInput();
    onViewTantalis(null);
    onClearCriticalConflicts();
    setJobResults([]);
    setSubmitError("");
  };

  const handleViewShapeToggle = (isEnabled: boolean): void => {
    if (!isEnabled) {
      onShapePreviewEnabledChange(false);
      onPreviewMessageChange("");
      onViewTantalis(null);
      onClearCriticalConflicts();
      return;
    }

    onClearCriticalConflicts();
    if (inputs.source !== SOURCE_TANTALIS) {
      return;
    }

    // Remove extra spaces from the start and end of each value.
    const fileNumber = inputs.fileNumber.trim();
    const dispositionId = inputs.dispositionId.trim();
    const parcelId = inputs.parcelId.trim();

    // All three are needed for the lookup. Show a message if any are empty.
    if (!fileNumber || !dispositionId || !parcelId) {
      onPreviewMessageChange("Enter a File Number, Disposition ID and Parcel ID first.");
      return;
    }

    // Clear any old message and send the values up.
    onShapePreviewEnabledChange(true);
    onPreviewMessageChange("");
    onViewTantalis({ fileNumber, dispositionId, parcelId });
  };

  const handleSourceChange = (source: string): void => {
    updateField("source", source);
    onShapePreviewEnabledChange(false);
    onPreviewMessageChange("");
    onViewTantalis(null);
    onClearCriticalConflicts();
  };

  function isResultsPayload(data: unknown): data is JobPayload[] {
    return (
      Array.isArray(data) &&
      data.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          typeof (item as JobPayload).job_id === "string" &&
          typeof (item as JobPayload).aoi_id === "string"
      )
    );
}

  // Test Results Submission handler (real one commented out below)
  async function handleTestSubmission() {
    setSubmitError("");

    try {
      const payload = await loadJSON<JobPayload[]>(
        resultsUrl,
        isResultsPayload
      );

      setJobResults(payload);

    } catch (error) {
      console.error("Download failed:", error);
      setSubmitError(
        error instanceof Error ? error.message : "Submission failed."
      );
    }
  }

  async function handleSubmission() {
    try {
      const formData = new FormData();
      formData.append("name", inputs.name.trim());
      formData.append("email", inputs.email.trim());
      formData.append("region", inputs.region);
      formData.append("source", inputs.source);
      formData.append("crown_file_number", inputs.fileNumber.trim());
      formData.append("disposition_number", inputs.dispositionId.trim());
      formData.append("parcel_number", inputs.parcelId.trim());
      formData.append("generate_maps", String(inputs.maps));
      formData.append("export_overlap_results", String(inputs.overlaps));
      if (inputs.uploadFiles[0]) {
        formData.append("upload_file", inputs.uploadFiles[0]);
      }

      console.log("FormData entries:");

      for (const [key, value] of formData.entries()) {
        console.log(`${key}:`, value);
      }

      const response = await fetch("/api/jobs", {
        method: "POST",
        body: formData,
      });
      console.log(response)

      if (!response.ok) {
        const errorDetails = await response.json();

        console.error("API validation error:", errorDetails);

        throw new Error(
          `Request failed: ${response.status} - ${JSON.stringify(errorDetails.detail)}`
        );
      }

      const data = await response.json();

      console.log(data);

    } catch (error) {
      console.error("Download failed:", error);
    }
  }

  // What appears on the page.
  return (
    <div className="form-container">
      <div className="full-width-field">
        <input
          className="ast-inline-input"
          aria-label="Name"
          name="name"
          placeholder="Name"
          value={inputs.name}
          onChange={(event) => updateField("name", event.currentTarget.value)}
        />
      </div>

      <div className="full-width-field">
        <input
          className="ast-inline-input"
          aria-label="Email"
          name="email"
          type="email"
          placeholder="Email"
          value={inputs.email}
          onChange={(event) => updateField("email", event.currentTarget.value)}
        />
      </div>

      <div className="region-select">
        <Select
          aria-label="Region"
          name="region"
          items={REGION_ITEMS}
          selectionMode="single"
          size="medium"
          placeholder="Select a Region"
          selectedKey={inputs.region || null}
          onSelectionChange={(key) => updateField("region", key == null ? "" : String(key))}
        />
      </div>

      <div className="source-container">
        {/* Source: choose a Tantalis lookup or an uploaded file. */}
        <RadioGroup
          label="Source"
          orientation="horizontal"
          name="source"
          value={inputs.source}
          onChange={handleSourceChange}
        >
          <Radio value={SOURCE_TANTALIS}>Tantalis</Radio>
          <Radio value={SOURCE_UPLOAD}>Upload</Radio>
        </RadioGroup>

        {/* Tantalis section. Always on the page, but only opens (with a CSS animation)
            when Tantalis is picked. The "expanded" class is what opens it. */}
        <div className={`source-details ${inputs.source === SOURCE_TANTALIS ? "expanded" : ""}`}>
          <div className="source-details-inner">
            <hr />
            {/* The three Tantalis identifiers. Also filled in automatically when a map shape is clicked. */}
            <input
              className="ast-inline-input"
              aria-label="File Number"
              name="fileNumber"
              placeholder="File Number"
              value={inputs.fileNumber}
              onChange={(event) => updateField("fileNumber", event.currentTarget.value)}
            />
            <input
              className="ast-inline-input"
              aria-label="Disposition ID"
              name="dispositionId"
              placeholder="Disposition ID"
              value={inputs.dispositionId}
              onChange={(event) => updateField("dispositionId", event.currentTarget.value)}
            />
            <input
              className="ast-inline-input"
              aria-label="Parcel ID"
              name="parcelId"
              placeholder="Parcel ID"
              value={inputs.parcelId}
              onChange={(event) => updateField("parcelId", event.currentTarget.value)}
            />
          </div>
        </div>

        {/* Upload section. Only opens when Upload is picked. */}
        <div className={`source-details ${inputs.source === SOURCE_UPLOAD ? "expanded" : ""}`}>
          <div className="source-details-inner">
            <hr />
            <p>Select File:</p>
            <div className="upload-input-row">
              <button type="button" onClick={() => fileInputRef.current?.click()}>
                Choose File
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="upload-file-input"
                accept=".shp,.zip,.geojson,.json,.kml"
                onChange={handleFileChange}
              />
              {inputs.uploadFiles.length > 0 && (
                <span className="upload-file-name">{selectedUploadPath}</span>
              )}
            </div>
            {/* Remove button. Only shown once a file is picked. */}
            {inputs.uploadFiles.length > 0 && (
              <button type="button" onClick={handleRemoveFile}>
                Remove file
              </button>
            )}
          </div>
        </div>
        {previewMessage && (
          <p className="tantalis-preview-message" role="status" aria-live="polite">
            {previewMessage}
          </p>
        )}
      </div>

      {/* On/off switches for the output options. */}
      <div className="switch-container">
        <Switch
          labelPosition="right"
          name="maps"
          isSelected={!inputs.maps}
          onChange={(value) => updateField("maps", !value)}
        >
          Do Not Generate Maps
        </Switch>

        <Switch
          labelPosition="right"
          name="overlaps"
          isSelected={!inputs.overlaps}
          onChange={(value) => updateField("overlaps", !value)}
        >
          Do Not Export Overlap Results
        </Switch>

        <Switch
          labelPosition="right"
          name="viewTantalis"
          isSelected={isShapePreviewEnabled}
          isDisabled={inputs.source !== SOURCE_TANTALIS}
          onChange={handleViewShapeToggle}
        >
          View Tantalis Shape on Map
        </Switch>

      </div>

      <div className="button-container">
        {/* Submit button. Note: there is no <form> around these fields and no submit
            function yet, so this button doesn't do anything at the moment. */}
        <Button onClick={handleSubmission} variant="primary" type="button">
          Submit
        </Button>
        <Button onClick={handleTestSubmission} variant="primary" type="button">
          Load Test Data
        </Button>
        {/* Clear button. type="button" so it never submits.
            onPress is the design system's version of onClick. */}
        <Button variant="secondary" type="button" onPress={handleClearAll}>
          Clear Form
        </Button>
      </div>

      {submitError && (
        <p className="results-error" role="alert">
          {submitError}
        </p>
      )}

      <ResultsWindow jobResults={jobResults} />
    </div>
  );
};

export default ASTForm;
