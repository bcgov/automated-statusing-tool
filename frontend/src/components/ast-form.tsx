import { useRef, useState, useEffect } from "react";
import { Button, Switch, Select, Radio, RadioGroup, TextField } from "@bcgov/design-system-react-components";
import "./ast-form.scss";

interface MapSelection {
  dispositionId: string;
  clickedAt: number;
}

interface ASTFormProps {
  mapSelection?: MapSelection | null;
}

// variable containing HTML to display in the 'root' node
const ASTForm: React.FC<ASTFormProps> = ({ mapSelection }) => {
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
  const [submissionMessage, setSubmissionMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputs({
      ...inputs,
      uploadFile: e.target.files?.[0] ?? null
    });
  };

  const handleRemoveFile = () => {
    setInputs(values => ({...values, uploadFile: null}));
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClearAll = () => {
    setInputs(initialInputs);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setSubmissionMessage("");

    const regionLabels: Record<string, string> = {
      cariboo: "Cariboo",
      kootenay: "Kootenay Boundary",
      northeast: "Northeast",
      omineca: "Omineca",
      skeena: "Skeena",
      south_coast: "South Coast",
      thompson_okanagan: "Thompson Okanagan",
      west_coast: "West Coast",
    };

    const payload = {
      user: inputs.name,
      date: new Date().toISOString().slice(0, 10),
      region: regionLabels[inputs.region] ?? inputs.region,
      area_of_interest: "",
      crown_file_number: inputs.fileNumber,
      disposition_number: inputs.dispositionId,
      parcel_number: inputs.parcelId,
      output_directory: "",
      suppress_map_creation: !inputs.maps,
      aoi_id: mapSelection?.dispositionId ?? "",
      aoi_name: "",
      aoi: {},
    };

    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail ?? `Job submission failed: ${response.status}`);
      }

      setSubmissionMessage(`Job queued: ${result.item.job_id}`);
    } catch (error) {
      setSubmissionMessage(
        error instanceof Error ? error.message : "Unable to submit the job."
      );
    } finally {
      setIsSubmitting(false);
    }
  };
  
  useEffect(() => {
    if (mapSelection) {
      setInputs((values) => ({
        ...values,
        parcelId: mapSelection.dispositionId,
      }));
    }
  }, [mapSelection]);

  return (
      <form className="form-container" onSubmit={handleSubmit}>
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
              </div>
            </div>

            <div className={`source-details ${inputs.source === "2" ? "expanded" : ""}`}>
              <div className="source-details-inner upload-inputs">
                <hr/>
                <p>Select File:</p>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                />

                {inputs.uploadFile && (
                  <div>
                    <p>Selected: {inputs.uploadFile.name}</p>
                    <button type="button" onClick={handleRemoveFile}>
                      Remove file
                    </button>
                  </div>
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
              <Button variant="primary" type="submit" isDisabled={isSubmitting}>
                {isSubmitting ? "Submitting..." : "Submit"}
              </Button>
              <Button variant="secondary" type="button" onClick={handleClearAll}>Clear Form</Button>
            </div>
            <p role="status" aria-live="polite">{submissionMessage}</p>
        </form>
    )
  }

export default ASTForm;