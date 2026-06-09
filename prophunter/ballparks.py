"""MLB ballparks coordinates + HR park factors."""
from __future__ import annotations

from typing import Dict, Tuple

BALLPARKS: Dict[str, Tuple[float, float, bool]] = {
    "Arizona Diamondbacks": (33.4455, -112.0667, False),
    "Atlanta Braves":       (33.8908, -84.4678,  True),
    "Baltimore Orioles":    (39.2839, -76.6217,  True),
    "Boston Red Sox":       (42.3467, -71.0972,  True),
    "Chicago Cubs":         (41.9484, -87.6553,  True),
    "Chicago White Sox":    (41.8299, -87.6338,  True),
    "Cincinnati Reds":      (39.0975, -84.5069,  True),
    "Cleveland Guardians":  (41.4962, -81.6852,  True),
    "Colorado Rockies":     (39.7559, -104.9942, True),
    "Detroit Tigers":       (42.3390, -83.0485,  True),
    "Houston Astros":       (29.7572, -95.3556,  False),
    "Kansas City Royals":   (39.0517, -94.4803,  True),
    "Los Angeles Angels":   (33.8003, -117.8827, True),
    "Los Angeles Dodgers":  (34.0739, -118.2400, True),
    "Miami Marlins":        (25.7781, -80.2197,  False),
    "Milwaukee Brewers":    (43.0280, -87.9712,  False),
    "Minnesota Twins":      (44.9817, -93.2776,  True),
    "New York Mets":        (40.7571, -73.8458,  True),
    "New York Yankees":     (40.8296, -73.9262,  True),
    "Athletics":            (38.7600, -121.2700, True),
    "Philadelphia Phillies":(39.9061, -75.1665,  True),
    "Pittsburgh Pirates":   (40.4469, -80.0057,  True),
    "San Diego Padres":     (32.7073, -117.1566, True),
    "San Francisco Giants": (37.7786, -122.3893, True),
    "Seattle Mariners":     (47.5914, -122.3325, False),
    "St. Louis Cardinals":  (38.6226, -90.1928,  True),
    "Tampa Bay Rays":       (27.7682, -82.6534,  False),
    "Texas Rangers":        (32.7473, -97.0847,  False),
    "Toronto Blue Jays":    (43.6414, -79.3894,  False),
    "Washington Nationals": (38.8730, -77.0074,  True),
}

PARK_FACTORS_HR: Dict[str, int] = {
    "Colorado Rockies": 118, "Cincinnati Reds": 115, "New York Yankees": 113,
    "Philadelphia Phillies": 108, "Boston Red Sox": 107, "Baltimore Orioles": 106,
    "Milwaukee Brewers": 105, "Atlanta Braves": 104, "Chicago Cubs": 103,
    "Houston Astros": 103, "Toronto Blue Jays": 102, "Texas Rangers": 102,
    "Minnesota Twins": 101, "Arizona Diamondbacks": 100, "Washington Nationals": 100,
    "Los Angeles Angels": 100, "St. Louis Cardinals": 99, "Chicago White Sox": 99,
    "Kansas City Royals": 98, "Detroit Tigers": 97, "Tampa Bay Rays": 96,
    "New York Mets": 96, "Cleveland Guardians": 95, "San Francisco Giants": 94,
    "Los Angeles Dodgers": 93, "Athletics": 92, "Pittsburgh Pirates": 92,
    "Seattle Mariners": 91, "Miami Marlins": 89, "San Diego Padres": 86,
}
