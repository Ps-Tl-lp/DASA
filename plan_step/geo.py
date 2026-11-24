"""Metres from the base to latitude and longitude, the way PX4 and our plans do it.

This is `helpers.metres_to_lat_lon` in platform_configs/px4.yaml.
"""

import math

# PX4's Earth radius (src/lib/geo/geo.h, CONSTANTS_RADIUS_OF_EARTH): PX4 treats the
# Earth as this sphere, not the WGS84 ellipsoid. With it the formula below reproduces
# the waypoint in our missions/simple.plan to the last digit.
EARTH_RADIUS_M = 6371000.0


def metres_to_lat_lon(north_m, east_m, base_lat, base_lon):
    """Latitude and longitude of a point `north_m` north and `east_m` east of the base.

    Flat earth on PX4's sphere. A metre north is the same fraction of a degree
    everywhere. A metre east is a larger fraction the further you are from the
    equator, because the circles of latitude shrink by cos(latitude). Within our
    flight area the distance from the base is off by a few millimetres at most
    (2.4 mm at 200 m north and 200 m east).
    """
    lat = base_lat + math.degrees(north_m / EARTH_RADIUS_M)
    lon = base_lon + math.degrees(
        east_m / (EARTH_RADIUS_M * math.cos(math.radians(base_lat)))
    )
    return lat, lon
