import React, { useState, useRef, useEffect } from "react";
//import { useAuth } from '../auth/AuthContext'
import { Header, Footer } from "@bcgov/design-system-react-components";
import { useMatch, Link } from "react-router-dom";

import geobcLogo from "../assets/geobc_logo.png";
//import HealthStatus from "./HealthStatus";
//import { useHealth } from "./HealthContext";

{/*
interface HeaderLinkProps {
  url: string;
  title: string;
  displayText: string;
}


const HeaderLink: React.FC<HeaderLinkProps> = ({url, title, displayText}) => {
  return (
    <Link className="header-link" to={url} title={title}
    >{displayText}</Link>
  );
};
*/}

const PageHeader = () => {
  return (
    <div className="bcgov-header">
      <Header 
        title="Automated Statusing Tool"
        logoLinkElement={<a href="/" title="Return home"></a>}
        logoImage={<img src={geobcLogo}
        alt="GeoBC Logo" 
        style={{ height: "30px" }} />}
      />
    </div>
  );
};

const PageFooter = () => {
  const isMapPage = useMatch("/map/*");

  if (isMapPage) {
    return null;
  }

  return (
    <div>
      <Footer/>
    </div>
  );
};

export { PageHeader, PageFooter };