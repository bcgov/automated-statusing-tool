import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

interface FormData {
  name: string;
  email: string;
  region: string;
  source: string;
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
  uploadFile: File | null;
  maps: boolean;
  overlaps: boolean;
}

interface ResultsPageState {
  formData?: FormData;
}

const YOUTUBE_EMBED_SRC =
  "https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&controls=1&rel=0";

const ResultsPage = () => {
  const [revealed, setRevealed] = useState(false);
  const bouncerRef = useRef<HTMLDivElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const location = useLocation();
  const { formData } = (location.state as ResultsPageState) ?? {};

  // DVD-logo-style bouncing text, started once the video is revealed.
  useEffect(() => {
    if (!revealed) return;

    let x = 40;
    let y = 40;
    let dx = 2.4;
    let dy = 2.0;

    const tick = () => {
      const el = bouncerRef.current;
      if (!el) return;

      const maxX = window.innerWidth - el.offsetWidth - 10;
      const maxY = window.innerHeight - el.offsetHeight - 10;

      x += dx;
      y += dy;

      if (x <= 0 || x >= maxX) dx *= -1;
      if (y <= 0 || y >= maxY) dy *= -1;

      x = Math.max(0, Math.min(x, maxX));
      y = Math.max(0, Math.min(y, maxY));

      el.style.left = `${x}px`;
      el.style.top = `${y}px`;

      animationFrameRef.current = requestAnimationFrame(tick);
    };

    animationFrameRef.current = requestAnimationFrame(tick);

    return () => {
      if (animationFrameRef.current !== null) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [revealed]);

  return (
    <div style={styles.page}>
      {!revealed && (
        <div style={styles.bait}>
        <div style={styles.results}>
            <h2>Results</h2>
            <p>{formData?.name}</p>
            <p>{formData?.email}</p>
            <p>{formData?.region}</p>
            <p>{formData?.source}</p>
            <p>{formData?.fileNumber}</p>
            <p>{formData?.dispositionId}</p>
            <p>{formData?.parcelId}</p>
            <p>{formData?.uploadFile ? formData.uploadFile.name : "No file uploaded"}</p>
            <p>{formData?.maps ? "Maps: Yes" : "Maps: No"}</p>
            <p>{formData?.overlaps ? "Overlaps: Yes" : "Overlaps: No"}</p>
          </div>
          <h1 style={styles.baitHeading}>📄 Document Ready for Review</h1>
          <p style={styles.baitText}>
            Your requested file has finished processing. Click below to view
            it.
          </p>
          <button style={styles.playBtn} onClick={() => setRevealed(true)}>
            Open Document
          </button>
        </div>
      )}

      {revealed && (
        <div style={styles.reveal}>
          <div ref={bouncerRef} style={styles.bouncer}>
            {formData?.name}'s Results
          </div>

          <div style={styles.videoWrap}>
            <iframe
              src={YOUTUBE_EMBED_SRC}
              style={styles.iframe}
              allow="autoplay; encrypted-media"
              allowFullScreen
              title="rickroll"
            />
          </div>

            <div style={styles.caption}>
            🎉 {formData?.name ? `${formData?.name}, you've` : "you've"} successfully submitted an AST request 🎉
            </div>
        </div>
      )}
    </div>
  );
};

const accent = "#ff2fb0";
const accent2 = "#2fd8ff";

const styles: Record<string, React.CSSProperties> = {
  page: {
    margin: 0,
    background: "#fff",
    color: "#fff",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    overflow: "hidden",
  },
  results: {
    display: "flex",
    flexDirection: "column",
    color: "#000",
    background: "#fdfdfd",
    border: "1px solid #ccc",
    padding: 20,
    borderRadius: 8,
    marginBottom: 20,
  },
  bait: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    padding: 24,
    gap: 20,
  },
  baitHeading: {
    fontSize: "clamp(20px, 4vw, 32px)",
    margin: 0,
  },
  baitText: {
    color: "#000",
    opacity: 0.7,
    maxWidth: 480,
    margin: 0,
  },
  playBtn: {
    background: `#003366`,
    border: "none",
    color: "#fff",
    fontSize: 18,
    fontWeight: 700,
    padding: "16px 36px",
    borderRadius: 999,
    cursor: "pointer",
  },
  reveal: {
    position: "fixed",
    inset: 0,
    background: "#000",
  },
  bouncer: {
    position: "absolute",
    fontWeight: 900,
    fontSize: "100px",
    color: accent2,
    letterSpacing: 2,
    whiteSpace: "nowrap",
    textShadow: "0 0 12px currentColor",
    pointerEvents: "none",
    zIndex: 5,
  },
  videoWrap: {
    position: "absolute",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  iframe: {
    width: "100%",
    height: "100%",
    border: 0,
  },
  caption: {
    position: "absolute",
    bottom: 150,
    left: 0,
    right: 0,
    textAlign: "center",
    fontSize: "clamp(22px, 5vw, 40px)",
    fontWeight: 900,
    color: "#fff",
    textShadow: `0 0 20px ${accent}, 0 0 40px ${accent}`,
    zIndex: 5,
  },
};

export default ResultsPage;