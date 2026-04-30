"""
utils/validators.py
-------------------
Input validation and sanity checks.
"""

import config


def validate_config() -> None:
    """
    Raise ValueError with a clear message if essential config is missing
    or obviously wrong.
    """
    errors = []

    if config.N2YO_API_KEY in ("", "CHANGE_ME", "your_api_key_here"):
        errors.append(
            "N2YO_API_KEY is not set. Add it to your .env file."
        )

    if not (-90 <= config.GROUND_LAT <= 90):
        errors.append(f"GROUND_LAT={config.GROUND_LAT} is out of range [-90, 90].")

    if not (-180 <= config.GROUND_LON <= 180):
        errors.append(f"GROUND_LON={config.GROUND_LON} is out of range [-180, 180].")

    if config.GROUND_ALT < 0:
        errors.append(f"GROUND_ALT={config.GROUND_ALT} must be ≥ 0.")

    if config.NORAD_ID <= 0:
        errors.append(f"NORAD_ID={config.NORAD_ID} must be a positive integer.")

    if errors:
        raise ValueError("Configuration error(s):\n  • " + "\n  • ".join(errors))


def validate_coordinates(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180
