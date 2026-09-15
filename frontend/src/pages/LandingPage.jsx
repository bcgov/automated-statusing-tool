import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactDOM from "react-dom/client";
// import useState hook from React
//import { stac_url, fetchSTACCatalog, fetchSTACCollections } from "../utils/stacUtils";
//import CopyUrlComponent from "../components/CopyUrlComponent";
import "./LandingPage.scss";
import { Button, Switch, Select, Radio, RadioGroup, Tooltip, TooltipTrigger, TextField } from "@bcgov/design-system-react-components";
const bcBackground = new URL("../assets/bc_background.png", import.meta.url).href;

// variable containing HTML to display in the 'root' node
function LandingPage() {
  const initialInputs = {
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

  const [inputs, setInputs] = useState(initialInputs);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    setInputs({
      ...inputs,
      uploadFile: e.target.files[0]
    });
  };

  const handleRemoveFile = () => {
    setInputs(values => ({...values, uploadFile: null}));
    fileInputRef.current.value = '';
  };

  const handleSubmit = (e) => {
    let analyses = '';
    if (inputs.tab1) analyses += 'tab1';
    if (inputs.tab2) analyses += 'tab2';
    if (inputs.tab3) analyses += 'tab3';
    alert(`${inputs.name} will recieve information for ${inputs.region} at ${inputs.email}`);
    event.preventDefault();
  }

  const handleClearAll = () => {
    setInputs(initialInputs);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="landing-page">
      {/* <div className="banner" style={{ backgroundImage: `url(${bcBackground})` }}></div> */}
      <div className="form-container">
      <form onSubmit={handleSubmit}>
      <div className="full-width-field">
        <TextField
          label="Name"
          name="name"
          placeholder="Enter your name"
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
          placeholder="Enter your email" 
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
          onSelectionChange={(value) =>
            setInputs(values => ({
              ...values,
              region: value
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

        {/* Show only when TANTALIS is selected */}
        {inputs.source === '1' && (
        <div className="tantalis-inputs">
          <hr/>
          <TextField label="File Number" placeholder="Enter file number" name="fileNumber" value={inputs.fileNumber || ""} onChange={(value) =>
            setInputs(values => ({
              ...values,
              fileNumber: value
            }))
          } />
          <TextField label="Disposition ID" placeholder="Enter disposition ID" name="dispositionId" value={inputs.dispositionId || ""} onChange={(value) =>
            setInputs(values => ({
              ...values,
              dispositionId: value
            }))
          } />
          <TextField label="Parcel ID" placeholder="Enter parcel ID" name="parcelId" value={inputs.parcelId || ""} onChange={(value) =>
            setInputs(values => ({
              ...values,
              parcelId: value
            }))
          } />
        </div>
        )}

        {inputs.source === '2' && (
          <div className="upload-inputs">
            <hr/>
            <label>
              Select File:
              <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              />
            </label>
              
            {inputs.uploadFile && (
              <div>
                <p>Selected: {inputs.uploadFile.name}</p>
                <button type="button" onClick={handleRemoveFile}>
                  Remove file
                </button>
              </div>
            )}
          </div>
        )}
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
          <Button variant="primary" type="submit" text="Submit" class="btn-primary">Submit</Button>
          <Button variant="secondary" type="submit" text="Clear All" class="btn-secondary" onClick={handleClearAll}>Clear Form</Button>
        </div>
      </form>
      </div>
    </div>
  )
}

export default LandingPage;