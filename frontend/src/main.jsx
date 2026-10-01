import ReactDOM from "react-dom/client";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
// import useState hook from React
import { useState } from 'react'
import { PageHeader, PageFooter } from "./components/bcgov-components.tsx";
import LandingPage from "./pages/LandingPage.jsx";
import "./index.css";


// createrRoot takes an HTML element
// render method defines what to render in HTML container
// result displays <div id="root"> element
// root is like a container for content, managed by React. can be any word

const appElement = document.getElementById("app"); 

if (appElement) {
  ReactDOM.createRoot(appElement).render(
    <Router>
      <PageHeader />
        <Routes>
          <Route path="/" element={<LandingPage />} />
        </Routes>
      <PageFooter />
    </Router>
  );
}