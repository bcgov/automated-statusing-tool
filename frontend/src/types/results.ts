
export interface JobPayload {
  job_id: string;
  aoi_id: string;
  execution_time: number;
  results: DatasetResult[];
}

export interface DatasetResult {
  dataset_id: string;
  dataset_name: string;
  status: string;
  error: string | null;
  parts: PartResult[];
}

export interface PartResult {
  aoi_part_id: string;
  part_index: number;
  part_area_ha: number;
  part_attributes: Record<string, unknown>;
  result: AnalysisResult;
}

export interface AnalysisResult {
  analysis_timestamp: string;
  registry: number | null;
  operator_type: string;
  spatial_link: string | null;
  total_area?: number | null;
  feature_count: number | null;
  measure_value: number | null;
  measure_unit: string | null;
  is_adjacent?: boolean | null;
  features: FeatureResult[];
}

export interface FeatureResult {
  feature_id: string;
  properties: Record<string, unknown>;
  measure: number;
}
