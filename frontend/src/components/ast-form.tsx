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

// updated week of sept 21: keep the form state and TANTALIS preview action together so the parcel can be reviewed from the map.
const ASTForm: React.FC<ASTFormProps> = ({ mapSelection, onViewTantalis }) => {
  const navigate = useNavigate();

  // Keep the form's field values in one object so the component can update and reset them consistently.
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

  // updated week of sept 21: keep the selected local upload in state so the user can review or remove it without losing other form entries.
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
            {/* Let the user choose between a direct TANTALIS lookup and an uploaded file, with the matching fields shown below. */}
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

            {/* Always mounted now — visibility is animated via CSS, not conditional rendering */}
            <div className={`source-details ${inputs.source === "1" ? "expanded" : ""}`}>
              <div className="source-details-inner tantalis-inputs">
                <hr/>
                {/* These fields collect the identifiers needed to preview a TANTALIS parcel in the map. */}
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
                {/* updated week of sept 21: allow the user to select an external file without adding the map preview behavior to the upload path. */}
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

            <div className="button-container">
              <Button variant="primary" type="submit">Submit</Button>
              <Button variant="secondary" type="submit" onClick={handleClearAll}>Clear Form</Button>
            </div>
        </div>
    )
  }

export default ASTForm;