import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactDOM from "react-dom/client";
// import useState hook from React
//import { stac_url, fetchSTACCatalog, fetchSTACCollections } from "../utils/stacUtils";
//import CopyUrlComponent from "../components/CopyUrlComponent";
import "./LandingPage.scss";
import { SubmitButton } from "../components/bcgov-components.tsx";
const bcBackground = new URL("../assets/bc_background.png", import.meta.url).href;

// variable containing HTML to display in the 'root' node
function LandingPage() {
  const [inputs, setInputs] = useState({uploadFile: null});

  const handleChange = (e) => {
    const target = e.target;
    const name = target.name;
    // if checkbox, select checked item
    const value = target.type === 'checkbox' ? target.checked : target.value;
    setInputs(values => ({...values, [name]: value}))
  }

  const handleFileChange = (e) => {
    setInputs({
      ...inputs,
      uploadFile: target.files[0]
    });
  };

  const handleSubmit = (e) => {
    let analyses = '';
    if (inputs.tab1) analyses += 'tab1';
    if (inputs.tab2) analyses += 'tab2';
    if (inputs.tab3) analyses += 'tab3';
    alert(`${inputs.name} will recieve information for ${inputs.region} at ${inputs.email}`);
    event.preventDefault();
  }

  return (
    <div className="landing-page">
      {/* <div className="banner" style={{ backgroundImage: `url(${bcBackground})` }}></div> */}
      <div className="form-container">
      <form onSubmit={handleSubmit}>
        <p><label>Name: 
        <input 
          type="text" 
          name="name" 
          value={inputs.name} 
          onChange={handleChange}
        />
        </label></p>
        <p><label>E-mail:
          <input 
            type="text" 
            name="email" 
            value={inputs.email} 
            onChange={handleChange}
          />
          </label></p>
          <p><label>Region: 
          <select value={inputs.region} onChange={handleChange}>
            <option value="cariboo">Cariboo</option>
            <option value="kootenay">Kootenay</option>
            <option value="northeast">Northeast</option>
            <option value="omineca">Omineca</option>
            <option value="skeena">Skeena</option>
            <option value="south_coast">South Coast</option>
            <option value="thompson_okanagan">Thompson Okanagan</option>
            <option value="west_coast">West Coast</option>
        </select>
        </label></p>

        <p>
        <label> Source:
          <input 
            type="radio" 
            name="source" 
            value="tantalis" 
            checked={inputs.source === 'tantalis'} 
            onChange={handleChange} 
          /> TANTALIS
        </label>
        <label>
          <input 
            type="radio" 
            name="source" 
            value="upload" 
            checked={inputs.source === 'upload'} 
            onChange={handleChange} 
          /> Upload
        </label></p>

        {/* Show only when TANTALIS is selected */}
        {inputs.source === 'tantalis' && (
        <div>
        <label>
        File Number:
        <input
        type="text"
        name="fileNumber"
        value={inputs.fileNumber}
        onChange={handleChange}
        />
        </label><br/>

        <label>
        Disposition ID:
        <input
        type="text"
        name="dispositionId"
        value={inputs.dispositionId}
        onChange={handleChange}
        />
        </label><br/>
        
        <label>
        Parcel ID:
        <input
        type="text"
        name="parcelId"
        value={inputs.parcelId}
        onChange={handleChange}
        />
        </label>
        </div>
        )}

        {inputs.source === 'upload' && (
          <div>
            <label>
              Select File:
              <input
              type="file"
              onChange={handleFileChange}
              />
            </label>
              
            {inputs.uploadFile && (
              <p>Selected: {inputs.uploadFile.name}</p>
            )}
          </div>
        )}

        <p><label>
        <input 
          type="checkbox" 
          className="styled-checkbox"
          name="maps" 
          checked={inputs.maps} 
          onChange={handleChange}
        /> Generate Maps
        </label><br/>
        <label>
          <input 
            type="checkbox" 
            className="styled-checkbox"
            name="overlaps" 
            checked={inputs.overlaps} 
            onChange={handleChange}
          /> Export Overlap Results
        </label></p>
        {/* <button type="submit">Submit</button> */}
        <SubmitButton type="submit" text="Submit" class="btn-primary"/>
          <p>Current values: {inputs.name} {inputs.email} {inputs.region} {inputs.tomato}</p>
      </form>
      </div>
    </div>
  )
}

export default LandingPage;