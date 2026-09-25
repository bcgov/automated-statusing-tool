import React, { useState } from "react";
import { Header, Footer, AlertBanner } from "@bcgov/design-system-react-components";

import geobcLogo from "../assets/geobc_logo.png";

//page header component
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

//page footer component
const PageFooter = () => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [selectedFooterItem, setSelectedFooterItem] = useState("");

  const footerLinks = [
    { label: "Disclaimer", value: "https://www2.gov.bc.ca/gov/content?id=79F93E018712422FBC8E674A67A70535" },
    { label: "Privacy", value: "https://www2.gov.bc.ca/gov/content?id=9E890E16955E4FF4BF3B0E07B4722932" },
    { label: "Accessibility", value: "https://www2.gov.bc.ca/gov/content?id=E08E79740F9C41B9B0C484685CC5E412" },
    { label: "Contact us", value: "https://www2.gov.bc.ca/gov/content?id=6A77C17D0CCB48F897F8598CCC019111" },
  ];

  //footer dropdown select handler
  const handleFooterSelect = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextValue = event.target.value;
    setSelectedFooterItem(nextValue);

    if (nextValue) {
      window.open(nextValue, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <>
      {isCollapsed ? (
        <button
          type="button"
          className="bcgov-footer-tab"
          aria-label="Show more information"
          title="Show more information"
          onClick={() => setIsCollapsed(false)}
        >
          More information
        </button>
      ) : (
        <div className={`bcgov-page-footer ${isExpanded ? "expanded" : "collapsed"}`}>
          <div className="bcgov-footer-toolbar">
            <div className="bcgov-footer-controls-left">
              <select
                id="bcgov-footer-select"
                className="bcgov-footer-select"
                value={selectedFooterItem}
                onChange={handleFooterSelect}
                aria-label="Select disclaimer information"
              >
                <option value="">More info</option>
                {footerLinks.map((item) => (
                  <option key={item.label} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>

              <button
                type="button"
                className="bcgov-footer-toggle"
                aria-expanded={isExpanded}
                aria-label={isExpanded ? "Collapse territorial acknowledgement" : "Expand territorial acknowledgement"}
                onClick={() => setIsExpanded((value) => !value)}
              >
                <span>{isExpanded ? "Hide Territorial Acknowledgement" : "Show Territorial Acknowledgement"}</span>
                <span className="bcgov-footer-arrow" aria-hidden="true">{isExpanded ? "↑" : "↓"}</span>
              </button>
            </div>

            <button
              type="button"
              className="bcgov-footer-collapse"
              aria-label="Collapse footer"
              title="Collapse footer"
              onClick={() => setIsCollapsed(true)}
            >
              <span>Collapse Footer</span>
              <span className="bcgov-footer-arrow" aria-hidden="true">↓</span>
            </button>
          </div>

          {isExpanded && (
            <div className="bcgov-footer-content">
              <Footer />
            </div>
          )}
        </div>
      )}
    </>
  );
};

const AlertBannerComponent = () => {
 const alertmessage = "This site is currently in development.";  

 return (
    <AlertBanner
      variant="info"
      isIconHidden={false}
      isCloseable={false}
      layout="fixed"
    >
      {alertmessage}<a href='https://github.com/bcgov/automated-statusing-tool' target='_blank' rel='noopener noreferrer' style={{ color: 'white', textDecoration: 'underline' }}>Learn more</a>
    </AlertBanner>
  );
}

export { PageHeader, PageFooter, AlertBannerComponent };