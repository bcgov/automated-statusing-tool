// React tools:
// useState = store a value that redraws the component when it changes.
import { useState } from "react";
// Types only. These add nothing to the final app.
// ChangeEvent = the event from a normal HTML input or dropdown. FC = "function component".
import type { ChangeEvent, FC } from "react";
// Ready-made page pieces from the BC Government design system.
import { Header, Footer, AlertBanner } from "@bcgov/design-system-react-components";

// The GeoBC logo shown in the header.
import geobcLogo from "../assets/geobc_logo.png";

// One link in the footer's "More info" dropdown.
interface FooterLink {
  label: string; // Text shown in the dropdown
  value: string; // Web address that opens when it's picked
}

// Start of every gov.bc.ca page address. Each link adds its own page id to the end.
const GOV_BC_BASE_URL = "https://www2.gov.bc.ca/gov/content?id=";

// Links in the footer's "More info" dropdown.
// Kept outside the components so the list isn't rebuilt on every redraw.
const FOOTER_LINKS: FooterLink[] = [
  { label: "Disclaimer", value: `${GOV_BC_BASE_URL}79F93E018712422FBC8E674A67A70535` },
  { label: "Privacy", value: `${GOV_BC_BASE_URL}9E890E16955E4FF4BF3B0E07B4722932` },
  { label: "Accessibility", value: `${GOV_BC_BASE_URL}E08E79740F9C41B9B0C484685CC5E412` },
  { label: "Contact us", value: `${GOV_BC_BASE_URL}6A77C17D0CCB48F897F8598CCC019111` },
];

// Text and link shown in the "in development" banner at the top of the app.
const ALERT_MESSAGE = "This site is currently in development.";
const PROJECT_REPO_URL = "https://github.com/bcgov/automated-statusing-tool";

// Page header: the BC Gov branded top bar with the site title and GeoBC logo.
const PageHeader: FC = () => {
  return (
    <div className="bcgov-header">
      <Header
        title="Automated Statusing Tool"
        // The logo is wrapped in this link, so clicking it goes back to the home page.
        logoLinkElement={<a href="/" title="Return home"></a>}
        // The logo image. alt text is read by screen readers.
        // Its size is set in index.scss (.bcgov-header img).
        logoImage={<img src={geobcLogo} alt="GeoBC Logo" />}
      />
    </div>
  );
};

// Page footer: a bar with the "More info" link dropdown,
// a button to show/hide the territorial acknowledgement,
// and a button to shrink the whole footer into a small tab.
const PageFooter: FC = () => {
  // Whether the territorial acknowledgement (the BC Gov footer) is showing. Starts hidden.
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  // Whether the whole footer is shrunk down to the small "More information" tab. Starts full size.
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

  // Runs when a link is picked in the dropdown. Opens that page in a new tab.
  const handleFooterSelect = (event: ChangeEvent<HTMLSelectElement>): void => {
    const nextValue = event.target.value;

    // Only open a page if a real link was picked (not the "More info" placeholder).
    if (nextValue) {
      // "noopener,noreferrer" is a security setting. It stops the new page
      // from being able to access or control this page.
      window.open(nextValue, "_blank", "noopener,noreferrer");
    }
  };

  // What appears on the page.
  // <> </> is an empty wrapper. It groups items without adding an extra <div>.
  return (
    <>
      {/* condition ? A : B means "if the condition is true show A, otherwise show B".
          Collapsed = show only the small tab. Not collapsed = show the full footer. */}
      {isCollapsed ? (
        // Small tab. Clicking it brings the full footer back.
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
        // Full footer. The "expanded" or "collapsed" class tells the CSS how to style it.
        <div className={`bcgov-page-footer ${isExpanded ? "expanded" : "collapsed"}`}>
          <div className="bcgov-footer-toolbar">
            {/* Left side of the footer bar. */}
            <div className="bcgov-footer-controls-left">
              {/* "More info" dropdown. Picking a link opens that policy page.
                  value="" keeps it showing "More info", so it resets after every pick. */}
              <select
                className="bcgov-footer-select"
                value=""
                onChange={handleFooterSelect}
                aria-label="Select disclaimer information"
              >
                {/* Placeholder option. Its empty value means "nothing picked". */}
                <option value="">More info</option>
                {/* One option for each link in FOOTER_LINKS.
                    key gives React a unique name for each option so it can track them. */}
                {FOOTER_LINKS.map((link) => (
                  <option key={link.label} value={link.value}>
                    {link.label}
                  </option>
                ))}
              </select>

              {/* Shows or hides the territorial acknowledgement.
                  aria-expanded tells screen readers whether it's open. */}
              <button
                type="button"
                className="bcgov-footer-toggle"
                aria-expanded={isExpanded}
                aria-label={isExpanded ? "Collapse territorial acknowledgement" : "Expand territorial acknowledgement"}
                onClick={() => setIsExpanded((isOpen) => !isOpen)}
              >
                <span>{isExpanded ? "Hide Territorial Acknowledgement" : "Show Territorial Acknowledgement"}</span>
                {/* Arrow points up when open, down when closed. Hidden from screen readers. */}
                <span className="bcgov-footer-arrow" aria-hidden="true">
                  {isExpanded ? "↑" : "↓"}
                </span>
              </button>
            </div>

            {/* Right side of the footer bar: shrinks the footer down to the small tab. */}
            <button
              type="button"
              className="bcgov-footer-collapse"
              aria-label="Collapse footer"
              title="Collapse footer"
              onClick={() => setIsCollapsed(true)}
            >
              <span>Collapse Footer</span>
              <span className="bcgov-footer-arrow" aria-hidden="true">
                ↓
              </span>
            </button>
          </div>

          {/* The BC Gov footer (with the territorial acknowledgement). Only shown when expanded. */}
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

// Alert banner: the blue "in development" message across the top of the app,
// with a link to the project's GitHub page.
const AlertBannerComponent: FC = () => {
  return (
    <AlertBanner
      variant="info" // Blue information style
      isIconHidden={false} // Show the info icon
      isCloseable={false} // Users can't close it
      layout="fixed"
    >
      {ALERT_MESSAGE}
      {/* Adds a space between the message and "Learn more". */}
      {" "}
      {/* Opens the GitHub page in a new tab. noopener noreferrer is the same security setting as above. */}
      <a
        href={PROJECT_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: "white", textDecoration: "underline" }}
      >
        Learn more
      </a>
    </AlertBanner>
  );
};

// Makes these three components available to other files (for example, App.tsx).
export { PageHeader, PageFooter, AlertBannerComponent };
