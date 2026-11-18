"""
Crown Land Status for a run: the link between the engine's results and the first tab.

The Crown Land Status tab reports what administrative areas the AOI falls in -
its mapsheets, districts, provincial forest, survey parcels, the nearest Indian
Reserve and archaeology site. The engine works those out the same way as every
other overlap: they are the datasets of the Tab 1 registry
(config/registry/tab1), run through the same operators. This module picks each
line's values out of that registry's results.

A dataset is found by the table it reads and the analysis run on it, not by its
name, so renaming a dataset in the registry does not empty a line on the report.

The tenure's own facts (applicant, tenure type, legal description...) are not
spatial. They are read from TANTALIS by the caller and handed in.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional, Sequence

from ast_engine.core.execution import ADJACENCY, NEAREST, OVERLAY, AnalysisTask
from ast_engine.core.results import AstResults, DatasetResultGroup, FeatureRecord

from .crown_land_status import TEXT_FAILED, TEXT_NOT_CHECKED, CrownLandStatus, Value

NO_INDIAN_RESERVE = "No Indian Reserve within 25km"
NO_ARCH_SITE = "No Arch Site within 25km"

# The tables the Crown Land Status lines are read from.
MAPSHEETS = "WHSE_BASEMAPPING.BCGS_20K_GRID"
NR_DISTRICTS = "WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP"
MUNICIPALITIES = "WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP"
PROV_FOREST = "WHSE_ADMIN_BOUNDARIES.FADM_PROV_FOREST"
PROV_FOREST_ADDITION = "WHSE_ADMIN_BOUNDARIES.FADM_PROV_FOREST_ADDITION"
PROV_FOREST_DELETION = "WHSE_ADMIN_BOUNDARIES.FADM_PROV_FOREST_DELETION"
PROV_FOREST_EXCLUSION = "WHSE_ADMIN_BOUNDARIES.FADM_PROV_FOREST_EXCLUSION"
ASSESSMENT_AREAS = "WHSE_TANTALIS.TA_ASSESSMENT_AREAS_SVW"
LAND_TITLE_DISTRICTS = "WHSE_TANTALIS.TA_LAND_TITLE_DISTRICTS_SVW"
ELECTORAL_DISTRICTS = "WHSE_ADMIN_BOUNDARIES.PED_PROV_ELECTORAL_DIST_POLY"
REGIONAL_DISTRICTS = "WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_REGIONAL_DISTRICTS_SP"
SURVEY_PARCELS = "WHSE_TANTALIS.TA_SURVEY_PARCELS_SVW"
RIGHT_OF_WAY_PARCELS = "WHSE_TANTALIS.TA_SURVEYED_ROW_PARCELS_SVW"
ALR = "WHSE_LEGAL_ADMIN_BOUNDARIES.OATS_ALR_POLYS"
ARCH_POTENTIAL = "WHSE_ARCHAEOLOGY.RAAD_AOA_PROVINCIAL"
ARCH_SITES = "WHSE_ARCHAEOLOGY.RAAD_TFM_SITES_SVW"
INDIAN_RESERVES = "WHSE_ADMIN_BOUNDARIES.ADM_INDIAN_RESERVES_BANDS_SP"


@dataclass(frozen=True)
class TenureFacts:
    """What TANTALIS says about the file the status is for.

    All empty for an uploaded AOI, which has no file, and when the worker has
    no BCGW connection to read them with.

    applicant_name  the interest holder on the disposition.
    received_dates  when the application was received.
    details         the tenure's attributes, by TANTALIS field name (see
                    tantalis_status.TENURE_FIELDS).
    """

    applicant_name: str = ""
    received_dates: tuple[str, ...] = ()
    details: Mapping[str, Sequence[str]] = field(default_factory=dict)


def build_crown_land_status(
    tasks: Sequence[AnalysisTask],
    results: AstResults,
    *,
    tab1_registry: str,
    run_date: date,
    run_by: str = "",
    region: str = "",
    crown_file_number: Optional[str] = None,
    disposition_number: Optional[str] = None,
    tenure: Optional[TenureFacts] = None,
) -> CrownLandStatus:
    """Build the Crown Land Status tab's contents from a run.

    tab1_registry  the name the Tab 1 registry was run under; only its datasets
                   are read here.

    A line whose dataset failed says "FAILED", and one whose dataset was not in
    the run - the Tab 1 registry was not loaded, or does not list it - says
    "Not checked", so neither can be taken for "none found".
    """
    tenure = tenure or TenureFacts()
    tab1 = _Tab1Results(tasks, results, tab1_registry)

    def detail(name: str) -> tuple[str, ...]:
        return tuple(tenure.details.get(name, ()))

    return CrownLandStatus(
        run_date=run_date,
        run_by=run_by,
        crown_file_number=crown_file_number or "",
        disposition_number=disposition_number or "",
        region=region,
        applicant_name=tenure.applicant_name,
        received_dates=tenure.received_dates,
        tenure_area_ha=detail("TENURE_AREA_IN_HECTARES"),
        tenure_location=detail("TENURE_LOCATION"),
        tenure_legal_description=detail("TENURE_LEGAL_DESCRIPTION"),
        tenure_type=detail("TENURE_TYPE"),
        tenure_subtype=detail("TENURE_SUBTYPE"),
        tenure_purpose=detail("TENURE_PURPOSE"),
        tenure_subpurpose=detail("TENURE_SUBPURPOSE"),
        parcel_numbers=detail("INTRID_SID"),
        mapsheets=tab1.values(MAPSHEETS, OVERLAY, "MAP_TILE_DISPLAY_NAME"),
        pins=tab1.values(SURVEY_PARCELS, OVERLAY, "PIN_SID", "PARCEL_LEGAL_DESCRIPTION"),
        pins_adjacent=tab1.values(SURVEY_PARCELS, ADJACENCY, "PIN_SID", "PARCEL_LEGAL_DESCRIPTION"),
        pins_right_of_way=tab1.values(RIGHT_OF_WAY_PARCELS, OVERLAY, "PIN_SID", "PARCEL_LEGAL_DESCRIPTION"),
        assessment_areas=tab1.values(ASSESSMENT_AREAS, OVERLAY, "ASSESSMENT_AREA_NAME"),
        regional_districts=tab1.values(REGIONAL_DISTRICTS, OVERLAY, "ADMIN_AREA_NAME"),
        municipalities=tab1.values(MUNICIPALITIES, OVERLAY, "ADMIN_AREA_NAME"),
        electoral_districts=tab1.values(ELECTORAL_DISTRICTS, OVERLAY, "ELECTORAL_DISTRICT_NAME"),
        provincial_forest=tab1.values(PROV_FOREST, OVERLAY, "PROV_FOREST_CD_DESCRIPTION", "MAP_BLOCK_ID"),
        provincial_forest_addition=tab1.values(PROV_FOREST_ADDITION, OVERLAY, "PROV_FOREST_CD_DESCRIPTION", "OIC_YEAR"),
        provincial_forest_addition2=tab1.values(PROV_FOREST_ADDITION, OVERLAY, "OIC_NUMBER", "MAP_BLOCK_ID"),
        provincial_forest_deletion=tab1.values(PROV_FOREST_DELETION, OVERLAY, "PROV_FOREST_CD_DESCRIPTION", "DOCUMENT_TYPE"),
        provincial_forest_deletion2=tab1.values(PROV_FOREST_DELETION, OVERLAY, "DELETION_YEAR"),
        provincial_forest_exclusion=tab1.values(PROV_FOREST_EXCLUSION, OVERLAY, "PROV_FOREST_CD_DESCRIPTION", "AREA_TYPE"),
        provincial_forest_exclusion2=tab1.values(PROV_FOREST_EXCLUSION, OVERLAY, "EXCLUSION_NUMBER"),
        forest_districts=tab1.values(NR_DISTRICTS, OVERLAY, "DISTRICT_NAME"),
        land_title_offices=tab1.values(LAND_TITLE_DISTRICTS, OVERLAY, "LAND_TITLE_DISTRICT_NAME"),
        in_alr=tab1.found(ALR, OVERLAY),
        nearest_indian_reserve=tab1.nearest(
            INDIAN_RESERVES,
            lambda feature, km: f"{_joined(feature, 'ENGLISH_NAME', 'BAND_NAME')} | {km} km(s)",
            none_found=NO_INDIAN_RESERVE,
        ),
        nearest_arch_site=tab1.nearest(
            ARCH_SITES,
            lambda feature, km: f"{km} (km) - {_joined(feature, 'BORDENNUMBER')}",
            none_found=NO_ARCH_SITE,
        ),
        arch_potential=tab1.values(ARCH_POTENTIAL, OVERLAY, "POTENTIAL"),
    )


class _Tab1Results:
    """The Tab 1 registry's results, looked up by table and analysis."""

    def __init__(self, tasks: Sequence[AnalysisTask], results: AstResults, tab1_registry: str):
        self._groups: dict[tuple[str, str], DatasetResultGroup] = {}
        for task, group in zip(tasks, results.results, strict=True):
            if task.source_registry == tab1_registry:
                self._groups[(task.datasource.upper(), task.operator)] = group

    def _features(self, datasource: str, operator: str) -> Optional[list[FeatureRecord]]:
        """A dataset's features across every part of the AOI.

        Returns None when the dataset failed. Raises KeyError when it was not run.
        """
        group = self._groups[(datasource, operator)]
        if group.status == "failure":
            return None
        return [feature for part in group.parts for feature in part.result.features]

    def values(self, datasource: str, operator: str, *fields: str) -> Value:
        """The different values of a dataset's field(s) among the features found, sorted.

        With two fields, each line reads "first - second"."""
        try:
            features = self._features(datasource, operator)
        except KeyError:
            return TEXT_NOT_CHECKED
        if features is None:
            return TEXT_FAILED
        lines = {_joined(feature, *fields) for feature in features}
        return tuple(sorted(line for line in lines if line))

    def found(self, datasource: str, operator: str) -> str:
        """ "Yes" when a dataset found anything on the AOI, otherwise "No"."""
        try:
            features = self._features(datasource, operator)
        except KeyError:
            return TEXT_NOT_CHECKED
        if features is None:
            return TEXT_FAILED
        return "Yes" if features else "No"

    def nearest(self, datasource: str, describe, *, none_found: str) -> str:
        """Describe the nearest feature of a dataset, with its distance in kilometres.

        describe(feature, km) writes the line. none_found is what the line says
        when the dataset found nothing within its search distance.
        """
        try:
            features = self._features(datasource, NEAREST)
        except KeyError:
            return TEXT_NOT_CHECKED
        if features is None:
            return TEXT_FAILED
        measured = [feature for feature in features if feature.measure is not None]
        if not measured:
            return none_found
        closest = min(measured, key=lambda feature: feature.measure)
        return describe(closest, round(closest.measure / 1000.0, 1))


def _joined(feature: FeatureRecord, *fields: str) -> str:
    """A feature's values for some fields, joined with " - ". A whole number
    is shown without ".0", and a field with no value is left out."""
    parts = []
    for name in fields:
        value = feature.properties.get(name)
        if value is None or value == "":
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        parts.append(str(value))
    return " - ".join(parts)
