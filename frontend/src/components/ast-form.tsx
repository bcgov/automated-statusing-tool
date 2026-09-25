import { useNavigate } from "react-router-dom";
import { useRef, useState, useEffect } from "react";
import { Button, Switch, Select, Radio, RadioGroup, TextField } from "@bcgov/design-system-react-components";
import "./ast-form.scss";

interface MapSelection {
  dispositionId: string;
  clickedAt: number;
}

interface TantalisPreviewRequest {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

interface ASTFormProps {
  mapSelection?: MapSelection | null;
  onViewTantalis?: (request: TantalisPreviewRequest) => void;
}

// ASTForm is the main data-entry form for the AST workflow.
// It captures contact information, region, source selection, and the TANTALIS identifiers used to preview a parcel on the map.
const ASTForm: React.FC<ASTFormProps> = ({ mapSelection, onViewTantalis }) => {
  const navigate = useNavigate();

  // Keep the form values in one object so state resets, updates, and map-driven prefills remain predictable.
  const initialInputs = {
    name: "" as string,
    email: "" as string,
    region: "" as string,
    source: "" as string,
    fileNumber: "" as string,
    dispositionId: "" as string,
    parcelId: "" as string,
    uploadFile: null as File | null,
    maps: false as boolean,
    overlaps: false as boolean,
  };

  const [inputs, setInputs] = useState(initialInputs);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Tracks the local upload file so the user can see the selected file name and remove it without losing other form data.
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputs({
      ...inputs,
      uploadFile: e.target.files?.[0] ?? null
    });
  };

  // updated week of sept 21: clear the uploaded file cleanly when the user removes it so the rest of the form remains unchanged.
  const handleRemoveFile = () => {
    setInputs(values => ({...values, uploadFile: null}));
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // updated week of sept 21: reset the form back to a clean state without leaving a stale file input behind.
  const handleClearAll = () => {
    setInputs(initialInputs);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // updated week of sept 21: when a parcel is selected from the map, fill the parcel ID field so the user can confirm the match.
  useEffect(() => {
    if (mapSelection) {
      setInputs((values) => ({
        ...values,
        parcelId: mapSelection.dispositionId,
      }));
    }
  }, [mapSelection]);

  // Push the TANTALIS identifiers up to the page so the map can query and highlight the matching shape.
  const handleViewTantalisInMap = () => {
    // updated week of sept 21: send the typed TANTALIS identifiers upward so the map can query and display the matching land parcel.
    const fileNumber = inputs.fileNumber.trim();
    const dispositionId = inputs.dispositionId.trim();
    const parcelId = inputs.parcelId.trim();

    if (!fileNumber || !dispositionId || !parcelId) {
      return;
    }

    onViewTantalis?.({
      fileNumber,
      dispositionId,
      parcelId,
    });
  };

  return (
        <div className="form-container">
          {/* Contact details are captured at the top of the form before the user selects the source of the parcel information. */}
          <div className="full-width-field">
            <TextField
              label="Name"
              name="name"
              value={inputs.name || ""}
              onChange={(value) =>
                setInputs(values => ({
                  ...values,
                  name: value
                }))
              }
            />
          </div>

          <div className="full-width-field">
            <TextField 
              label="Email" 
              name="email" 
              type="email" 
              value={inputs.email || ""} 
              onChange={(value) =>
                setInputs(values => ({
                  ...values,
                  email: value
                }))
              } 
            />
          </div>
            
          <Select
            label="Region"
            name="region"
            items={[
              { id: "cariboo", label: "Cariboo" },
              { id: "kootenay", label: "Kootenay" },
              { id: "northeast", label: "Northeast" },
              { id: "omineca", label: "Omineca" },
              { id: "skeena", label: "Skeena" },
              { id: "south_coast", label: "South Coast" },
              { id: "thompson_okanagan", label: "Thompson Okanagan" },
              { id: "west_coast", label: "West Coast" },
            ]}
            selectionMode="single"
            size="medium"
            selectedKey={inputs.region || null}
            onSelectionChange={(key) =>
              setInputs((values) => ({
                ...values,
                region: key as string,
              }))
            }
          />

          <div className="source-container">
            {/* The source selector controls which data path the user wants to review: either a direct TANTALIS lookup or a local uploaded dataset. */}
            <RadioGroup
              label="Source"
              orientation="horizontal"
              name="source"
              value={inputs.source}
              onChange={(value) =>
                setInputs(values => ({
                  ...values,
                  source: value,
                }))
              }
            >
              <Radio value="1">
                TANTALIS
              </Radio>

              <Radio value="2">
                Upload
              </Radio>
            </RadioGroup>

            {/* The TANTALIS section is always mounted and expanded conditionally for a smoother form experience. */}
            <div className={`source-details ${inputs.source === "1" ? "expanded" : ""}`}>
              <div className="source-details-inner tantalis-inputs">
                <hr/>
                {/* These identifiers are required to query the public TANTALIS parcel layer and map the parcel in context. */}
                <TextField 
                  label="File Number" 
                  name="fileNumber" 
                  value={inputs.fileNumber || ""} 
                  onChange={(value) =>
                    setInputs(values => ({
                      ...values,
                      fileNumber: value
                    }))
                  } 
                />
                <TextField 
                  label="Disposition ID" 
                  name="dispositionId" 
                  value={inputs.dispositionId || ""} 
                  onChange={(value) =>
                    setInputs(values => ({
                      ...values,
                      dispositionId: value
                    }))
                  } 
                />
                <TextField 
                  label="Parcel ID" 
                  name="parcelId" 
                  value={inputs.parcelId || ""} 
                  onChange={(value) =>
                    setInputs(values => ({
                      ...values,
                      parcelId: value
                    }))
                  } 
                />

                <div className="tantalis-preview-row">
                  <button
                    type="button"
                    className="tantalis-preview-link"
                    onClick={handleViewTantalisInMap}
                  >
                    View shape on map
                  </button>
                </div>
              </div>
            </div>

            <div className={`source-details ${inputs.source === "2" ? "expanded" : ""}`}>
              <div className="source-details-inner upload-inputs">
                <hr/>
                {/* The upload path allows a user to attach a local dataset without enabling the map preview behavior for that file type. */}
                <p>Select File:</p>
                <div className="upload-input-row">
                  <input
                    type="file"
                    accept=".geojson,.json,.kml,.shp"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                  />

                  {inputs.uploadFile && (
                    <span className="upload-file-name">{inputs.uploadFile.name}</span>
                  )}
                </div>

                {inputs.uploadFile && (
                  <button type="button" onClick={handleRemoveFile}>
                    Remove file
                  </button>
                )}
              </div>
            </div>
          </div>

            {/* These switches represent optional workflow outputs such as generated maps and overlap checks. */}
            <div className="switch-container">
              <Switch
                labelPosition="right"
                name="maps"
                isSelected={inputs.maps}
                onChange={(value) =>
                  setInputs(values => ({
                    ...values,
                    maps: value,
                  }))
                }
              >
                Generate Maps
              </Switch>

              <Switch
                labelPosition="right"
                name="overlaps"
                isSelected={inputs.overlaps}
                onChange={(value) =>
                  setInputs(values => ({
                    ...values,
                    overlaps: value,
                  }))
                }
              >
                Export Overlap Results
              </Switch>
            </div>

            {/* Submission and reset actions stay at the bottom of the form so the user can finish the workflow or start over cleanly. */}
            <div className="button-container">
              <Button variant="primary" type="submit">Submit</Button>
              <Button variant="secondary" type="submit" onClick={handleClearAll}>Clear Form</Button>
            </div>
        </div>
    )
  }

export default ASTForm;