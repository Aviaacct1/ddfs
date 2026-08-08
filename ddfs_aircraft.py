"""Avia DDFS - aircraft classification. One owner for the ICAO code letter.

Author: Avia Solutions.

The ICAO aerodrome reference code letter by OAG aircraft code, wingspan-based.
Imported, never restated. Until 8 August 2026 this map was defined three times:
in ddfs_service.py and ddfs_ladder.py identically at 47 entries, and in
ddfs_zagreb_oracle.py at 33 entries with the same values but fourteen types
missing, so the oracle classified those fourteen as C through the default.
Eleven of the fourteen are widebodies that should be D, E or F.

A constant kept equal in two places by a comment is a constant with no owner.
"""

# Default for an unlisted type. C is the narrowbody assumption: right for the
# great majority of movements, and wrong in the expensive direction for a
# widebody, so an unlisted type appearing in a real schedule should be added
# here rather than left to the default.
DEFAULT_CODE = "C"

ICAO = {
    # code B
    "AT4": "B", "CRJ": "B", "SF3": "B",
    # code C
    "221": "C", "223": "C", "290": "C", "295": "C", "319": "C", "320": "C", "321": "C",
    "32A": "C", "32B": "C", "32N": "C", "32Q": "C", "738": "C", "739": "C", "73H": "C",
    "7M8": "C", "7M9": "C", "AT7": "C", "CR9": "C", "DH4": "C", "E70": "C", "E75": "C",
    "E90": "C", "E95": "C",
    # code D
    "752": "D", "763": "D", "764": "D",
    # code E
    "332": "E", "333": "E", "339": "E", "343": "E", "351": "E", "359": "E", "35K": "E",
    "744": "E", "772": "E", "773": "E", "77L": "E", "77W": "E", "781": "E", "787": "E",
    "788": "E", "789": "E",
    # code F
    "388": "F", "748": "F",
}


def code_letter(aircraft_code):
    """The ICAO code letter for an OAG aircraft code. Unlisted types take
    DEFAULT_CODE; callers that care should count how often that happens."""
    return ICAO.get(aircraft_code, DEFAULT_CODE)
