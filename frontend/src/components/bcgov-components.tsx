// React tools:
// useState = store a value that redraws the component when it changes.
import { useState } from "react";
// Types only. These add nothing to the final app.
// FC = "function component".
import type { FC, FormEvent, RefObject } from "react";
// Ready-made page pieces from the BC Government design system.
import { Footer } from "@bcgov/design-system-react-components";

// The GeoBC logo shown in the top bar.
import geobcLogo from "../assets/geobc_logo_white.png";

// Colours and font shared by the top bar and the map footer bar. BC blue background with white text.
const HEADER_BACKGROUND = "#013366";
const HEADER_TEXT = "#ffffff";
const HEADER_FONT = '"BC Sans", "Noto Sans", Verdana, Arial, sans-serif';
// Colour of the map scale bar lines and blocks (BC gold). The scale numbers stay white.
const SCALE_BAR_COLOUR = "#fcba19";

// Colours for the map footer bar (scale bar, Support, More Information).
// The popup menus that open above it are not changed.
const FOOTER_STYLES = `
  .map-frame-footer {
    background: ${HEADER_BACKGROUND} !important;
    color: ${HEADER_TEXT} !important;
    border-top: 0.25px solid #011a33 !important;
  }
  .map-frame-footer .map-frame-footer__more {
    background: transparent !important;
    color: ${HEADER_TEXT} !important;
    border-color: ${HEADER_TEXT} !important;
  }
  .map-frame-footer .map-frame-footer__scale,
  .map-frame-footer .map-frame-footer__scale * {
    color: ${HEADER_TEXT} !important;
    border-color: ${SCALE_BAR_COLOUR} !important;
  }
  .map-frame-footer .map-frame-footer__scale [class*="singlebar-odd"] {
    background-color: ${SCALE_BAR_COLOUR} !important;
  }
  .map-frame-footer .map-frame-footer__scale [class*="singlebar-even"] {
    background-color: transparent !important;
  }
`;

// One link in the map-frame footer.
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
];

const SUPPORT_LINKS: FooterLink[] = [
  {
    label: "AST Intranet Page",
    value: "https://intranet.gov.bc.ca/intranet/content?id=3E0EC1527C4B4750A5595AF07BBD6E54",
  },
  { label: "Contact FrontCounter BC", value: "mailto:FCBCIntranet-SharePointSupport@gov.bc.ca" },
];

const MIN_SCALE_DENOMINATOR = 1_000;
const MAX_SCALE_DENOMINATOR = 10_000_000;
const PRESET_SCALES = [
  1_000,
  2_500,
  5_000,
  10_000,
  25_000,
  50_000,
  100_000,
  250_000,
  500_000,
  1_000_000,
  2_500_000,
  5_000_000,
  MAX_SCALE_DENOMINATOR,
];

// Compact footer information for the bottom edge of the map.
// Change: the former page-level collapsible footer now stays with the map frame.
interface MapFrameFooterProps {
  scaleBarTargetRef: RefObject<HTMLDivElement | null>;
  onScaleChange: (scaleDenominator: number) => void;
}

const MapFrameFooter: FC<MapFrameFooterProps> = ({ scaleBarTargetRef, onScaleChange }) => {
  const [isMoreInformationOpen, setIsMoreInformationOpen] = useState(false);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [isAcknowledgementOpen, setIsAcknowledgementOpen] = useState(false);
  const [isScaleMenuOpen, setIsScaleMenuOpen] = useState(false);
  const [customScale, setCustomScale] = useState("");
  const [scaleInputError, setScaleInputError] = useState("");

  const applyCustomScale = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const match = customScale.trim().match(/^(?:1\s*:\s*)?([\d,]+)$/);
    const denominator = match ? Number(match[1].replaceAll(",", "")) : Number.NaN;
    if (
      !Number.isFinite(denominator) ||
      denominator < MIN_SCALE_DENOMINATOR ||
      denominator > MAX_SCALE_DENOMINATOR
    ) {
      setScaleInputError("Enter a scale from 1:1,000 to 1:10,000,000 (provincial scale).");
      return;
    }

    onScaleChange(denominator);
    setScaleInputError("");
    setCustomScale("");
    setIsScaleMenuOpen(false);
  };

  return (
    <>
      <style>{FOOTER_STYLES}</style>
      {isAcknowledgementOpen && (
        <div className="map-frame-acknowledgement" role="region" aria-label="Territorial acknowledgement">
          <button
            type="button"
            className="map-frame-acknowledgement__close"
            aria-label="Close territorial acknowledgement"
            onClick={() => setIsAcknowledgementOpen(false)}
          >
            ×
          </button>
          <Footer hideLogoAndLinks hideCopyright />
        </div>
      )}
      {isScaleMenuOpen && (
        <div className="map-frame-footer__scale-menu" role="group" aria-label="Preset map scales">
          <div className="map-frame-footer__scale-menu-header">
            <span>Map scale</span>
            <button
              type="button"
              className="map-frame-footer__menu-close"
              aria-label="Close scale options"
              title="Close scale options"
              onClick={() => setIsScaleMenuOpen(false)}
            >
              ×
            </button>
          </div>
          {PRESET_SCALES.map((scale) => (
            <button
              type="button"
              key={scale}
              onClick={() => {
                onScaleChange(scale);
                setScaleInputError("");
                setIsScaleMenuOpen(false);
              }}
            >
              1:{scale.toLocaleString()}
            </button>
          ))}
          <form className="map-frame-footer__custom-scale" onSubmit={applyCustomScale}>
            <label htmlFor="custom-map-scale">Custom scale</label>
            <input
              id="custom-map-scale"
              type="text"
              inputMode="numeric"
              placeholder="1:500,000"
              value={customScale}
              aria-invalid={Boolean(scaleInputError)}
              aria-describedby={scaleInputError ? "custom-map-scale-error" : undefined}
              onChange={(event) => {
                setCustomScale(event.currentTarget.value);
                setScaleInputError("");
              }}
            />
            {scaleInputError && (
              <span id="custom-map-scale-error" className="map-frame-footer__scale-error" role="alert">
                {scaleInputError}
              </span>
            )}
            <button type="submit">Apply scale</button>
          </form>
        </div>
      )}
      <div className="map-frame-footer" role="contentinfo" aria-label="Map and policy information">
        <div
          ref={scaleBarTargetRef}
          className="map-frame-footer__scale"
          role="button"
          tabIndex={0}
          aria-label="Choose map scale"
          aria-haspopup="menu"
          aria-expanded={isScaleMenuOpen}
          onClick={() => setIsScaleMenuOpen((isOpen) => !isOpen)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setIsScaleMenuOpen((isOpen) => !isOpen);
            }
          }}
        >
        </div>
        <div className="map-frame-footer__actions">
          <div className="map-frame-footer__support">
            <button
              type="button"
              className="map-frame-footer__more"
              aria-expanded={isSupportOpen}
              aria-haspopup="menu"
              onClick={() => {
                setIsSupportOpen((isOpen) => !isOpen);
                setIsMoreInformationOpen(false);
              }}
            >
              Support <span aria-hidden="true">↑</span>
            </button>
            {isSupportOpen && (
              <nav className="map-frame-footer__menu" role="menu" aria-label="Support">
                <button
                  type="button"
                  className="map-frame-footer__menu-close"
                  role="menuitem"
                  aria-label="Close Support"
                  title="Close Support"
                  onClick={() => setIsSupportOpen(false)}
                >
                  ×
                </button>
                {SUPPORT_LINKS.map((link) => (
                  <a
                    key={link.label}
                    href={link.value}
                    target={link.value.startsWith("mailto:") ? undefined : "_blank"}
                    rel={link.value.startsWith("mailto:") ? undefined : "noopener noreferrer"}
                    role="menuitem"
                  >
                    {link.label}
                  </a>
                ))}
              </nav>
            )}
          </div>
          <div className="map-frame-footer__information">
            <button
              type="button"
              className="map-frame-footer__more"
              aria-expanded={isMoreInformationOpen}
              aria-haspopup="menu"
              onClick={() => {
                setIsMoreInformationOpen((isOpen) => !isOpen);
                setIsSupportOpen(false);
              }}
            >
              More Information <span aria-hidden="true">↑</span>
            </button>
            {isMoreInformationOpen && (
              <nav className="map-frame-footer__menu" role="menu" aria-label="More information">
                <button
                  type="button"
                  className="map-frame-footer__menu-close"
                  role="menuitem"
                  aria-label="Close More Information"
                  title="Close More Information"
                  onClick={() => setIsMoreInformationOpen(false)}
                >
                  ×
                </button>
                {FOOTER_LINKS.map((link) => (
                  <a
                    key={link.label}
                    href={link.value}
                    target="_blank"
                    rel="noopener noreferrer"
                    role="menuitem"
                  >
                    {link.label}
                  </a>
                ))}
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setIsMoreInformationOpen(false);
                    setIsAcknowledgementOpen(true);
                  }}
                >
                  Territorial Acknowledgement
                </button>
              </nav>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

// Text and link shown on the right of the top bar.
const ALERT_MESSAGE = "This site is currently in development.";
const PROJECT_REPO_URL = "https://github.com/bcgov/automated-statusing-tool";

// The top bar: one blue bar with the GeoBC logo and site title on the left
// and the "in development" notice on the right.
const AlertBannerComponent: FC = () => {
  return (
    <div
      className="bcgov-top-bar"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 12,
        boxSizing: "border-box",
        width: "100%",
        padding: "10px 24px",
        borderBottom: "0.5px solid #011a33",
        background: HEADER_BACKGROUND,
        color: HEADER_TEXT,
        fontFamily: HEADER_FONT,
      }}
    >
      {/* Logo and title. Clicking them goes back to the home page. */}
      <a
        href="/"
        title="Return home"
        style={{ display: "flex", alignItems: "flex-end", gap: 12, color: HEADER_TEXT, textDecoration: "none" }}
      >
        <img src={geobcLogo} alt="GeoBC Logo" style={{ display: "block", height: 28, width: "auto" }} />
        <span
          style={{
            fontFamily: '"Times New Roman", Times, serif',
            fontSize: "2.1rem",
            lineHeight: 0.8, // Keeps the title shorter than the logo, so the logo sets the bar height
            marginBottom: -2, // Nudges the text so its bottom lines up with the bottom of the logo
            fontWeight: 700,
            fontVariant: "small-caps",
            letterSpacing: "0.04em",
            color: HEADER_TEXT,
          }}
        >
          Automated Status Tool
        </span>
      </a>

      {/* In development notice, on the right. */}
      <div
        style={{
          alignSelf: "flex-end",
          fontFamily: HEADER_FONT,
          fontSize: "1.05rem",
          lineHeight: 1,
          textAlign: "right",
          color: HEADER_TEXT,
        }}
        > 
        {ALERT_MESSAGE}{" "}
        <a
          href={PROJECT_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: HEADER_TEXT, textDecoration: "underline" }}
        >
          Learn more
        </a>
      </div>
    </div>
  );
};

// Makes these components available to other files (for example, main.tsx).
export { MapFrameFooter, AlertBannerComponent };
