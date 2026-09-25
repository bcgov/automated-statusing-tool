import ReactDOM from "react-dom/client";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
// import useState hook from React
import { useState } from 'react'
import { PageHeader, PageFooter, AlertBannerComponent } from "./components/bcgov-components";
import LandingPage from "./pages/LandingPage";
import "./index.scss";

// This is the application entry point for the front-end app.
// It mounts React into the HTML shell and configures the top-level routing and page layout.
// The app currently exposes a single route: the landing page for the AST workflow.
const appElement = document.getElementById("app"); 

if (appElement) {
  ReactDOM.createRoot(appElement).render(
    <Router>
      {/* Site-wide alert banner shown at the top of the app to communicate status or development context. */}
      <AlertBannerComponent />
      {/* Shared BC Gov page shell appears above the routed page content. */}
      <PageHeader />
        <Routes>
          {/* The landing page holds the form and the map preview workflow for the TANTALIS review experience. */}
          <Route path="/" element={<LandingPage />} />
        </Routes>
      {/* Shared BC Gov footer and policy links appear below the main content. */}
      <PageFooter />
    </Router>
  );
}