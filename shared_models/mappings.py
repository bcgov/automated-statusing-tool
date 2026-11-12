from .models import Regions, REGION_TO_ORG_UNIT


def region_to_org_unit(region: Regions | str) -> str:
    """Convert a recognized region name or enum member to its ORG_UNIT."""
    return REGION_TO_ORG_UNIT[Regions(region)]