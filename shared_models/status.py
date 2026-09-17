# shared_models/status.py
from enum import StrEnum

class JobStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"