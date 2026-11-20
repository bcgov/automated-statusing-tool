import type { FC } from "react";
import type { CriticalConflictError, CriticalConflictLayer } from "../types/tantalis";

interface CriticalConflictsPanelProps {
  layers: CriticalConflictLayer[];
  errors: CriticalConflictError[];
  isChecking: boolean;
  isOpen: boolean;
  selectedLayerName: string | null;
  status: string;
  onClose: () => void;
}

const LAYER_GUIDANCE = "Guidance coming soon.";

const CriticalConflictsPanel: FC<CriticalConflictsPanelProps> = ({
  layers,
  errors,
  isChecking,
  isOpen,
  selectedLayerName,
  status,
  onClose,
}) => {
  if (!isOpen) {
    return null;
  }

  const selectedLayer = layers.find((layer) => layer.name === selectedLayerName);

  return (
    <section className="critical-conflicts-panel" role="region" aria-label="Critical conflicts">
      <header className="critical-conflicts-panel__header">
        <h2>Critical conflicts</h2>
        <button type="button" aria-label="Close critical conflicts" title="Close" onClick={onClose}>
          ×
        </button>
      </header>

      <div className="critical-conflicts-panel__body">
        {isChecking && (
          <p role="status" aria-live="polite">
            Checking critical conflicts...
          </p>
        )}
        {status && (
          <p role="status" aria-live="polite">
            {status}
          </p>
        )}
        {!isChecking && !status && layers.length === 0 && errors.length === 0 && (
          <p role="status" aria-live="polite">
            No critical conflicts found.
          </p>
        )}
        {selectedLayer ? (
          <article className="critical-conflicts-panel__layer">
            <h3>{selectedLayer.label}</h3>
            <h4>Layer Description</h4>
            <p>{selectedLayer.description}</p>
            <h4>Layer Guidance</h4>
            <p>{LAYER_GUIDANCE}</p>
          </article>
        ) : (
          layers.length > 0 && (
            <div className="critical-conflicts-panel__layer-list">
              {layers.map((layer) => (
                <p key={layer.name}>{layer.label}</p>
              ))}
              <p>Hover over a highlighted area for details.</p>
            </div>
          )
        )}
        {errors.length > 0 && (
          <div className="critical-conflicts-panel__errors" role="status" aria-live="polite">
            {errors.map((error) => (
              <p key={error.layerName}>
                Could not check {error.layerLabel}: {error.message}
              </p>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

export default CriticalConflictsPanel;
