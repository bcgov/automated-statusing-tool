export interface TantalisIdentifiers {
  fileNumber: string;
  dispositionId: string;
  parcelId: string;
}

export interface CriticalConflictsRequest {
  clickedAt: number;
}

export interface CriticalConflictLayer {
  name: string;
  label: string;
  description: string;
}

export interface CriticalConflictError {
  layerName: string;
  layerLabel: string;
  message: string;
}
