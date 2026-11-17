"""Small, explicit place list.

Deliberately conservative and hand-maintained rather than inferred: a place name
is used to decide whether two reports describe the same event, so a wrong entry
merges two stories that should stay apart. Anything not listed here is simply
not treated as a place, which is the safe failure mode.
"""

from __future__ import annotations

from app.text.normalize import entity_key

PLACES: frozenset[str] = frozenset(
    {
        # India — states, union territories and major cities
        "india", "delhi", "new delhi", "mumbai", "chennai", "kolkata",
        "bengaluru", "bangalore", "hyderabad", "pune", "ahmedabad", "jaipur",
        "lucknow", "patna", "bhopal", "chandigarh", "gurugram", "gurgaon",
        "noida", "kochi", "surat", "nagpur", "indore", "visakhapatnam",
        "kerala", "tamil nadu", "karnataka", "maharashtra", "gujarat",
        "rajasthan", "punjab", "haryana", "bihar", "odisha", "assam",
        "telangana", "andhra pradesh", "uttar pradesh", "madhya pradesh",
        "west bengal", "jharkhand", "chhattisgarh", "uttarakhand",
        "himachal pradesh", "goa", "manipur", "nagaland", "mizoram", "tripura",
        "meghalaya", "arunachal pradesh", "sikkim", "ladakh", "puducherry",
        "jammu and kashmir", "kashmir", "srinagar", "jammu", "sriharikota",
        # World
        "united states", "us", "usa", "america", "washington", "new york",
        "california", "texas", "china", "beijing", "shanghai", "russia",
        "moscow", "ukraine", "kyiv", "pakistan", "islamabad", "karachi",
        "bangladesh", "dhaka", "sri lanka", "colombo", "nepal", "kathmandu",
        "bhutan", "myanmar", "afghanistan", "kabul", "maldives",
        "united kingdom", "uk", "britain", "london", "france", "paris",
        "germany", "berlin", "italy", "rome", "spain", "madrid",
        "netherlands", "brussels", "geneva", "switzerland", "sweden",
        "norway", "denmark", "finland", "poland", "turkey", "ankara",
        "japan", "tokyo", "south korea", "seoul", "north korea",
        "israel", "gaza", "west bank", "iran", "tehran", "iraq", "baghdad",
        "syria", "lebanon", "saudi arabia", "riyadh", "qatar", "doha",
        "united arab emirates", "dubai", "abu dhabi", "egypt", "cairo",
        "singapore", "malaysia", "indonesia", "jakarta", "thailand",
        "vietnam", "philippines", "australia", "sydney", "melbourne",
        "perth", "canberra", "new zealand", "canada", "ottawa", "toronto",
        "brazil", "argentina", "mexico", "south africa", "nigeria", "kenya",
        "ethiopia", "european union", "africa", "asia", "europe",
    }
)


# Indian states, union territories and cities — the subset of PLACES that makes
# a story a domestic one. Kept explicit for the same reason as the list above.
INDIA_PLACES: frozenset[str] = frozenset(
    {
        "india", "delhi", "new delhi", "mumbai", "chennai", "kolkata",
        "bengaluru", "bangalore", "hyderabad", "pune", "ahmedabad", "jaipur",
        "lucknow", "patna", "bhopal", "chandigarh", "gurugram", "gurgaon",
        "noida", "kochi", "surat", "nagpur", "indore", "visakhapatnam",
        "kerala", "tamil nadu", "karnataka", "maharashtra", "gujarat",
        "rajasthan", "punjab", "haryana", "bihar", "odisha", "assam",
        "telangana", "andhra pradesh", "uttar pradesh", "madhya pradesh",
        "west bengal", "jharkhand", "chhattisgarh", "uttarakhand",
        "himachal pradesh", "goa", "manipur", "nagaland", "mizoram", "tripura",
        "meghalaya", "arunachal pradesh", "sikkim", "ladakh", "puducherry",
        "jammu and kashmir", "kashmir", "srinagar", "jammu", "sriharikota",
        # Further cities: enough to place a story, never used to split one.
        "thiruvananthapuram", "coimbatore", "madurai", "varanasi", "kanpur",
        "agra", "amritsar", "ludhiana", "guwahati", "bhubaneswar", "ranchi",
        "raipur", "dehradun", "shimla", "mysuru", "mangaluru", "vijayawada",
        "nashik", "thane", "vadodara", "rajkot", "jodhpur", "udaipur",
        "meerut", "ghaziabad", "faridabad", "prayagraj", "ayodhya", "gwalior",
        "jabalpur", "navi mumbai", "itanagar", "imphal", "aizawl", "kohima",
        "shillong", "gangtok", "agartala", "panaji", "leh", "puri", "cuttack",
        "siliguri", "kozhikode", "thrissur", "tirupati", "warangal",
        "hubballi", "belagavi", "salem", "jalandhar", "patiala", "rohtak",
        "panipat", "sonipat", "ambala", "manesar", "amaravati", "kota",
    }
)

# City-level names only. Countries and regions are deliberately excluded from
# the disambiguation set below: one outlet writing "India" while another writes
# "New Delhi" describes the same event, so treating those as conflicting
# locations would split stories that belong together. Two different *cities*,
# on the other hand, almost always mean two different events.
CITIES: frozenset[str] = frozenset(
    {
        "delhi", "mumbai", "chennai", "kolkata", "bengaluru", "hyderabad",
        "pune", "ahmedabad", "jaipur", "lucknow", "patna", "bhopal",
        "chandigarh", "gurugram", "noida", "kochi", "surat", "nagpur",
        "indore", "visakhapatnam", "srinagar", "jammu", "sriharikota",
        "washington", "new york", "beijing", "shanghai", "moscow", "kyiv",
        "islamabad", "karachi", "dhaka", "colombo", "kathmandu", "kabul",
        "london", "paris", "berlin", "rome", "madrid", "brussels", "geneva",
        "ankara", "tokyo", "seoul", "tehran", "baghdad", "riyadh", "doha",
        "dubai", "abu dhabi", "cairo", "jakarta", "sydney", "melbourne",
        "perth", "canberra", "ottawa", "toronto",
    }
)

FOREIGN_PLACES: frozenset[str] = frozenset(
    PLACES - INDIA_PLACES - {"asia", "europe", "africa", "us", "uk"}
) | frozenset({"u.s.", "america", "britain", "european union"})

# Different names for one place. Without these, "New Delhi" and "Delhi" would
# look like two cities and split a story in half.
CITY_ALIASES: dict[str, str] = {
    "new delhi": "delhi",
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "gurgaon": "gurugram",
    "poona": "pune",
    "peking": "beijing",
    "kiev": "kyiv",
}


def _canonical(key: str) -> str:
    return CITY_ALIASES.get(key, key)


def is_place(entity: str) -> bool:
    return entity_key(entity) in PLACES


def _keys_within(entity: str) -> set[str]:
    """Every place-shaped name inside a surface form.

    Entities arrive as phrases — "Delhi Metro Rail Corporation" — so matching
    the whole string against the gazetteer finds nothing. Word runs inside the
    phrase are checked instead.
    """
    words = entity_key(entity).split()
    found: set[str] = set()
    for size in (2, 1):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i : i + size])
            canonical = _canonical(candidate)
            if canonical in PLACES or canonical in CITIES:
                found.add(canonical)
    return found


def _phrases_in(text: str, names: frozenset[str]) -> set[str]:
    """Names from ``names`` that occur in ``text`` as whole words."""
    words = entity_key(text).split()
    found: set[str] = set()
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i : i + size])
            if candidate in names:
                found.add(_canonical(candidate))
    return found


def india_places_in(text: str) -> set[str]:
    return _phrases_in(text, INDIA_PLACES)


def foreign_places_in(text: str) -> set[str]:
    """Places outside India named in ``text``.

    Continents are left out: "Asia" in a headline says nothing about whether a
    story is domestic. So is "West Bengal", which contains no foreign place
    however the words are split.
    """
    found = _phrases_in(text, FOREIGN_PLACES)
    # "West Bank" is foreign; "west" on its own is not a place at all, and the
    # two-word match above already handled it.
    return found


def places_in(entities: list[str]) -> set[str]:
    found: set[str] = set()
    for entity in entities:
        found |= _keys_within(entity)
    return found


def cities_in(entities: list[str]) -> set[str]:
    """Only city-level names, canonicalised. Used to separate lookalike events."""
    return {key for key in places_in(entities) if key in CITIES}
