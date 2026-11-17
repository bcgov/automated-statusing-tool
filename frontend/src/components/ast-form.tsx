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
import type { TantalisIdentifiers } from "../types/tantalis";
// Styles for this form.
import "./ast-form.scss";

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
  uploadFile: File | null;
  maps: boolean; // Generate Maps switch (true = on)
  overlaps: boolean; // Export Overlap Results switch (true = on)
}

// A submitted job, as the API reports it.
// status is one of: Queued, Processing, Publishing, Completed, Failed.
// error says why the job failed. It is null unless status is Failed.
interface SubmittedJob {
  jobId: string;
  status: string;
  error: string | null;
}

// One of a job's maps, as the API lists them.
// name is used to open the map. title is the text shown for it.
interface JobMap {
  name: string;
  title: string;
}

// Values for the two Source radio buttons.
const SOURCE_TANTALIS = "1";
const SOURCE_UPLOAD = "2";

// The statuses a job ends on. Once a job reaches one of these it will not change again.
const JOB_STATUS_COMPLETED = "Completed";
const JOB_STATUS_FAILED = "Failed";

// How often to ask the API how a running job is doing, in milliseconds.
const JOB_POLL_INTERVAL_MS = 3000;

// File types the API accepts for an uploaded shape.
// A shapefile is several files, so it has to be uploaded as one .zip.
const UPLOAD_FILE_TYPES = ".geojson,.json,.kml,.kmz,.gpkg,.zip";

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
// The id is also sent to the API, which uses it to pick the region's list of datasets,
// so each id has to match the region name used there (for example "kootenay_boundary").
const REGION_ITEMS = [
  { id: "cariboo", label: "Cariboo" },
  { id: "kootenay_boundary", label: "Kootenay Boundary" },
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
  // The job created by the last Submit, or null if nothing has been submitted yet.
  const [job, setJob] = useState<SubmittedJob | null>(null);
  // The maps made for the submitted job. Empty until the job completes, and for
  // a job submitted with Generate Maps off.
  const [jobMaps, setJobMaps] = useState<JobMap[]>([]);
  // Message shown under the buttons when a submission is refused. Empty = no message.
  const [submitMessage, setSubmitMessage] = useState<string>("");
  // True while a submission is being sent, so Submit can't be clicked twice.
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
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
    setSubmitMessage("");
    setJob(null);
    setJobMaps([]);
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

  // While a job is running, ask the API for its status every few seconds.
  // Stops once the job is Completed or Failed, and when the form is cleared.
  useEffect(() => {
    // Nothing submitted yet, or the job has already finished.
    if (!job || job.status === JOB_STATUS_COMPLETED || job.status === JOB_STATUS_FAILED) {
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/jobs/${job.jobId}`);
        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }
        const data = await response.json();
        // Saving a new object each time (even when the status is unchanged)
        // makes this effect run again, which is what schedules the next check.
        setJob({ jobId: job.jobId, status: data.status, error: data.error ?? null });
      } catch (error) {
        console.error("Job status check failed:", error);
        // Keep checking. One failed request shouldn't stop the updates.
        setJob({ ...job });
      }
    }, JOB_POLL_INTERVAL_MS);
    // If the job changes or the form goes away before the timer fires, cancel it.
    return () => window.clearTimeout(timer);
  }, [job]);

  // Once the job completes, ask the API which maps were made for it.
  // jobId and status are read into their own values so this runs when one of
  // them changes, not on every status check.
  const jobId = job?.jobId;
  const jobStatus = job?.status;
  useEffect(() => {
    if (!jobId || jobStatus !== JOB_STATUS_COMPLETED) {
      return;
    }
    // Lets a response that arrives after the form was cleared be ignored.
    let cancelled = false;
    fetch(`/api/jobs/${jobId}/maps`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }
        return response.json();
      })
      .then((maps: JobMap[]) => {
        if (!cancelled) {
          setJobMaps(maps);
        }
      })
      .catch((error) => {
        // The results are still available without the maps list.
        console.error("Job maps request failed:", error);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, jobStatus]);

  // Runs when Submit is clicked. Sends the form to the API, which queues the job.
  async function handleSubmission() {
    setSubmitMessage("");
    setJobMaps([]);
    setIsSubmitting(true);
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
      if (inputs.uploadFile) {
        formData.append("upload_file", inputs.uploadFile);
      }

      // A path with no host, so the request goes to wherever this page was served from.
      // In development, vite.config.js forwards anything under /api to the API.
      const response = await fetch("/api/jobs", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (!response.ok) {
        // The API explains a refused job in "detail". When that is plain text
        // (for example "The file holds no shapes.") show it. Otherwise a field
        // is missing or wrong, and the detail is a list meant for developers.
        setSubmitMessage(
          typeof data.detail === "string"
            ? data.detail
            : "The job could not be submitted. Check that every field is filled in.",
        );
        return;
      }

      setJob({ jobId: data.item.job_id, status: data.item.status, error: null });
    } catch (error) {
      console.error("Submission failed:", error);
      setSubmitMessage("The job could not be submitted. Try again in a moment.");
    } finally {
      setIsSubmitting(false);
    }
  }

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
          <div className="source-details-inner">
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
              <button type="button" className="tantalis-preview-link" onClick={handleViewTantalisInMap}>
                View shape on map
              </button>
            </div>
            {previewMessage && (
              <p className="tantalis-preview-message" role="status" aria-live="polite">
                {previewMessage}
              </p>
            )}
          </div>
        </div>

        {/* Upload section. Only opens when Upload is picked. */}
        <div className={`source-details ${inputs.source === SOURCE_UPLOAD ? "expanded" : ""}`}>
          <div className="source-details-inner">
            <hr />
            <p>Select File:</p>
            <div className="upload-input-row">
              {/* File picker. accept limits it to these spatial file types. */}
              <input
                type="file"
                accept={UPLOAD_FILE_TYPES}
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
        {/* Submit button. Sends the form to the API. Turned off while a submission is being sent. */}
        <Button onClick={handleSubmission} variant="primary" type="button" isDisabled={isSubmitting}>
          {isSubmitting ? "Submitting..." : "Submit"}
        </Button>
        {/* Clear button. type="button" so it never submits.
            onPress is the design system's version of onClick. */}
        <Button variant="secondary" type="button" onPress={handleClearAll}>
          Clear Form
        </Button>
      </div>

      {/* Why the last submission was refused. Only shown when there is a message. */}
      {submitMessage && (
        <p className="job-status-message" role="alert">
          {submitMessage}
        </p>
      )}

      {/* The submitted job and how it is doing. Updates by itself while the job runs.
          role="status" and aria-live let screen readers announce each change. */}
      {job && (
        <div className="job-status" role="status" aria-live="polite">
          <p>
            Job {job.jobId}: <strong>{job.status}</strong>
          </p>
          {job.status === JOB_STATUS_FAILED && job.error && <p>{job.error}</p>}
          {job.status === JOB_STATUS_COMPLETED && (
            <a href={`/api/jobs/${job.jobId}/results`} target="_blank" rel="noreferrer">
              View results
            </a>
          )}
          {/* The job's maps, the overview first. Each opens in a new tab.
              Only shown when the job made maps. */}
          {jobMaps.length > 0 && (
            <ul className="job-maps">
              {jobMaps.map((map) => (
                <li key={map.name}>
                  <a href={`/api/jobs/${job.jobId}/maps/${map.name}`} target="_blank" rel="noreferrer">
                    {map.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default ASTForm;
