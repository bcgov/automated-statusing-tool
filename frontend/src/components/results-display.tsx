
import { useRef, useState } from "react";
import type { FC } from "react";
import type { JobPayload } from "../types/results";
import { formatDateTime, roundToTwo, toSentenceCase } from "../utils/formatters";

import "./results-display.scss";

interface ResultsWindowProps {
  jobResults: JobPayload[];
}

const ResultsWindow: FC<ResultsWindowProps> = ({ jobResults }) => {
  const resultsDialogRef = useRef<HTMLDialogElement | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobPayload | null>(null);

  if (!jobResults.length) return null;

  return (
    <section className="results-container" aria-label="Job details">
      <h2>Job Details</h2>

      <ul className="results-list">
        {jobResults.map((job) => (
          <li key={job.job_id}>
            <strong>Job ID:</strong>{" "}
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedJob(job);
                resultsDialogRef.current?.showModal();
              }}
            >
              {job.job_id}
            </button>
            <br />
            <strong>AOI ID:</strong> {job.aoi_id}
            <br />
            <strong>Status:</strong> Complete
          </li>
        ))}
      </ul>

      <dialog
        ref={resultsDialogRef}
        className="results-dialog"
        aria-labelledby="results-dialog-title"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            resultsDialogRef.current?.close();
          }
        }}
      >
        {selectedJob && (
          <>
            <div className="results-dialog-header">
              <div>
                <h2 id="results-dialog-title">
                  Job ID: {selectedJob.job_id}
                </h2>
                <p><strong>AOI ID:</strong> {selectedJob.aoi_id}</p>
                <p>
                  <strong>Execution Time:</strong>{" "}
                  {selectedJob.execution_time}s
                </p>
              </div>

              <button
                type="button"
                onClick={() => resultsDialogRef.current?.close()}
              >
                Close
              </button>
            </div>

            <div className="results-dialog-content">
              {selectedJob.results.map((dataset) => (
                <article
                  className="result-dataset"
                  key={dataset.dataset_id}
                >
                  <h3>{dataset.dataset_name}</h3>

                  <p><strong>Dataset ID:</strong> {dataset.dataset_id}</p>
                  <p><strong>Status:</strong> {dataset.status}</p>

                  {dataset.error && (
                    <p className="results-error">
                      <strong>Error:</strong> {dataset.error}
                    </p>
                  )}

                  {dataset.parts.map((part) => (
                    <section
                      className="result-part"
                      key={part.aoi_part_id}
                    >
                      <h4>Part {part.part_index}</h4>

                      <p>
                        <strong>AOI Part ID:</strong> {part.aoi_part_id}
                      </p>
                      <p>
                        <strong>Part Area:</strong> {roundToTwo(part.part_area_ha)} ha
                      </p>
                      {/* <p>
                        <strong>Part Attributes:</strong>{" "}
                        {JSON.stringify(part.part_attributes)}
                      </p> */}

                      <section className="result-analysis">
                        <h5>{toSentenceCase(part.result.operator_type)} - Analysis Result</h5>

                        <p>
                          <strong>Timestamp:</strong>{" "}
                          {formatDateTime(part.result.analysis_timestamp)}
                        </p>
                        <p>
                          <strong>Registry:</strong>{" "}
                          {part.result.registry ?? "N/A"}
                        </p>
                        <p>
                          <strong>Operator Type:</strong>{" "}
                          {part.result.operator_type}
                        </p>
                        <p>
                          <strong>Spatial Link:</strong>{" "}
                          {part.result.spatial_link ?? "N/A"}
                        </p>
                        <p>
                          <strong>Total Area:</strong>{" "}
                          {roundToTwo(part.result.total_area) ?? "N/A"}
                        </p>
                        <p>
                          <strong>Feature Count:</strong>{" "}
                          {part.result.feature_count ?? "N/A"}
                        </p>
                        <p>
                          <strong>Measure Value:</strong>{" "}
                          {roundToTwo(part.result.measure_value) ?? "N/A"}{" "}
                          {part.result.measure_unit ?? ""}
                        </p>

                        {part.result.is_adjacent !== undefined && (
                          <p>
                            <strong>Adjacent:</strong>{" "}
                            {part.result.is_adjacent === null
                              ? "N/A"
                              : part.result.is_adjacent
                                ? "Yes"
                                : "No"}
                          </p>
                        )}

                        <h6>Features</h6>

                        {part.result.features.length > 0 ? (
                          <table className="results-feature-table">
                            <thead>
                              <tr>
                                <th>Feature ID</th>
                                <th>Properties</th>
                                <th>Measure</th>
                              </tr>
                            </thead>
                            <tbody>
                              {part.result.features.map((feature) => (
                                <tr key={feature.feature_id}>
                                  <td>{feature.feature_id}</td>
                                  <td>
                                    {Object.entries(feature.properties).map(
                                      ([key, value]) => (
                                        <div key={key}>
                                          <strong>{key}:</strong>{" "}
                                          {String(value)}
                                        </div>
                                      )
                                    )}
                                  </td>
                                  <td>{roundToTwo(feature.measure)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <p>No features returned.</p>
                        )}
                      </section>
                    </section>
                  ))}
                </article>
              ))}
            </div>
          </>
        )}
      </dialog>
    </section>
  );
};

export { ResultsWindow };
