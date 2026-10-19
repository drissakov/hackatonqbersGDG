"""Finite OSM tag allowlist for D02's city leisure corpus.

Order resolves records with several matching tags. No tag implies price,
accessibility, quietness, sockets, opening hours, or an indoor location.
"""

CATEGORY_FILTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "museum": (("tourism", "museum"),),
    "culture": (
        ("amenity", "theatre"),
        ("amenity", "arts_centre"),
        ("amenity", "library"),
        ("tourism", "gallery"),
        ("historic", "monument"),
        ("historic", "memorial"),
    ),
    "food": (
        ("amenity", "cafe"),
        ("amenity", "restaurant"),
        ("amenity", "fast_food"),
        ("amenity", "food_court"),
        ("amenity", "ice_cream"),
        ("amenity", "bar"),
        ("amenity", "pub"),
    ),
    "walk": (
        ("leisure", "park"),
        ("leisure", "garden"),
        ("leisure", "nature_reserve"),
        ("tourism", "viewpoint"),
    ),
    "sport": (
        ("leisure", "sports_centre"),
        ("leisure", "fitness_centre"),
        ("leisure", "stadium"),
        ("leisure", "swimming_pool"),
        ("leisure", "ice_rink"),
        ("leisure", "pitch"),
    ),
    "shopping": (("shop", "mall"), ("amenity", "marketplace")),
    "entertainment": (
        ("amenity", "cinema"),
        ("leisure", "amusement_arcade"),
        ("leisure", "bowling_alley"),
        ("leisure", "water_park"),
        ("leisure", "playground"),
        ("tourism", "theme_park"),
        ("tourism", "zoo"),
    ),
}


def category_for(tags: dict[str, str]) -> str | None:
    """Return the first explicit allowlisted activity; never infer from a name."""
    for category, selectors in CATEGORY_FILTERS.items():
        if any(tags.get(key) == value for key, value in selectors):
            return category
    return None
