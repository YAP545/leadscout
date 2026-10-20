"""Tunable vocabulary, weights and thresholds. Edit here; no code changes needed."""

# ---- Courses -------------------------------------------------------------
# Specific forms first; the generic entry is only used if no specific form matches.
COURSES = {
    "Bharatanatyam": r"bhara(?:t|th)a?[\s-]?natyam",
    "Kathak": r"\bkathak\b",
    "Kuchipudi": r"\bkuchipudi\b",
    "Odissi": r"\bodissi\b",
    "Mohiniyattam": r"\bmohiniyattam\b",
    "Kathakali": r"\bkathakali\b",
    "Manipuri": r"\bmanipuri\b",
    "Sattriya": r"\bsattriya\b",
}
GENERIC_COURSE = (
    "Indian classical (general)",
    r"indian classical dance|classical indian dance|semi[\s-]?classical|classical dance",
)

# ---- Locations (first match wins; specific before broad) ------------------
LOCATIONS = [
    ("Mumbai, India", r"\bmumbai\b"), ("Pune, India", r"\bpune\b"),
    ("Delhi, India", r"\b(new )?delhi\b"), ("Bengaluru, India", r"\b(bengaluru|bangalore)\b"),
    ("Chennai, India", r"\bchennai\b"), ("Hyderabad, India", r"\bhyderabad\b"),
    ("Kolkata, India", r"\b(kolkata|calcutta)\b"), ("Chandigarh, India", r"\bchandigarh\b"),
    ("Ahmedabad, India", r"\bahmedabad\b"), ("Jaipur, India", r"\bjaipur\b"),
    ("Kochi, India", r"\bkochi\b"), ("Gurugram, India", r"\b(gurugram|gurgaon)\b"),
    ("Noida, India", r"\bnoida\b"), ("Nagpur, India", r"\bnagpur\b"),
    ("India", r"\bin india\b|\bacross india\b"),
    ("USA", r"(?-i:\bUSA?\b)|\bunited states\b|\bcalifornia\b|\btexas\b|\bnew jersey\b|\bnew york\b|\bnyc\b"),
    ("UK", r"(?-i:\bUK\b)|\bunited kingdom\b|\blondon\b"),
    ("Canada", r"\bcanada\b|\btoronto\b"),
    ("Australia", r"\baustralia\b|\bsydney\b|\bmelbourne\b"),
    ("UAE", r"\bdubai\b|\buae\b|\babu dhabi\b"),
    ("Singapore", r"\bsingapore\b"),
    ("Europe", r"(?-i:\bEU\b)|\beurope\b|\bgermany\b|\bnetherlands\b"),
]

# ---- Signal lexicons: (regex, weight, short name used in the 'reason' column) ----
SEEKER_SIGNALS = [
    (r"\b(looking for|searching for|in search of)\b", 1.5, "looking for"),
    (r"\b(can|could) (anyone|someone|you) (please )?(suggest|recommend|help)\b", 2.0, "asks for suggestions"),
    (r"\b(anyone|anybody)\b.{0,40}\b(recommend|suggest|idea|know|tried)\b", 1.5, "asks the community"),
    (r"\b(?:want(?:s|ed)?|wish(?:es|ed)?|would like|interested|planning|trying|(?<!\bno )(?<!\bnot )\bneed(?:s|ed)?)\s+(?:(?:to|in)\s+)?(?:learn(?:ing)?|join|enrol{1,2}(?:ing)?|register|start|take)\b", 2.0, "wants to learn/join"),
    (r"\bwhere (can|do|to) (i|we) (learn|find|take)\b", 2.0, "asks where to learn"),
    (r"\b(need|require|seeking) (a |an )?(good )?(online )?(teacher|tutor|guru|class|classes|instructor)\b", 2.0, "needs a teacher"),
    (r"\b(my|our) (wife|husband|daughter|son|kid|child|mother|mom)\b.{0,60}\b(looking|learn|enrol|enroll|join|classes)\b", 1.5, "family member learning"),
    (r"\b(recommend(ations?)?|suggest(ions)?)\b", 1.0, "asks for recommendations"),
    (r"\b(?:(?:can|could|may)\s+(?:i|we)\s+(?:learn|join|enrol{1,2}|take|start|apply)|is it possible to\s+(?:learn|join|start))\b", 2.0, "asks if they can learn/join"),
    (r"\bhow\b.{0,30}\b(?:join|enrol{1,2}|register|apply|contact|connect)\b", 2.5, "asks how to join"),
    (r"\b(?:(?:online\s+)?class(?:es)?\b.{0,15}\bavailable|available\b.{0,15}\b(?:online\s+)?class(?:es)?)\b", 2.0, "asks if classes available"),
    (r"^\s*[\W_]*(?:fees?|fees?\s+details)[\W_]*$|\b(what('?s| is| are) (the )?fees?|fees? kya hai|fees? kitn[ie]|how much)\b|fees?\?", 2.0, "asks about fees"),
    (r"\bhow (do|can|to) (i |we )?(start|begin|learn|find)\b", 1.5, "asks how to start"),
    (r"\b(is|are) there any\b", 1.0, "asks if any exist"),
    (r"\b(is|are) there\b(?:\s+(?:any|a|an|online|dance|classical))*\s+(?:class(?:es)?|course(?:s)?|batch(?:es)?)\b", 2.0, "asks if classes exist"),
    (r"\bdo you (offer|have|conduct) (any )?(online )?classes\b", 2.0, "asks if classes offered"),
    (r"\bkeep looking for a teacher\b|\bgoogling about\b", 1.0, "searching"),
]
PROVIDER_SIGNALS = [
    (r"\b(we|i) (offer|teach|provide|conduct)\b", 2.0, "we offer/I teach"),
    (r"\bfree (demo |trial )?class(es)?\b", 2.0, "free demo class"),
    (r"\b(rate|hourly fees?|per class|per hour)\b|/hr\b", 1.5, "pricing"),
    (r"\b(years? of (teaching )?experience|teaching experience)\b", 2.0, "teacher credentials"),
    (r"\bpay as you go\b", 2.0, "pay as you go"),
    (r"\brecommendations come from\b", 3.0, "teacher profile page"),
    (r"\bteacher'?s profile\b", 2.0, "teacher profile page"),
    (r"\b(message|contact|email|dm) me\b", 1.5, "contact me"),
    (r"\bif (anyone|anybody|you) (is|are) looking for\b", 2.0, "pitch to prospects"),
    (r"\bclasses near me\b", 1.5, "SEO listicle"),
    (r"\b(enrol+ now|register (now|for)|find my teacher)\b", 2.0, "enrol-now CTA"),
    (r"\b(sops?|embassy|consulate|ministry|iccr)\b", 2.5, "institutional notice"),
    (r"\bhighly recommend\b", 1.5, "testimonial"),
    (r"\b(certificate course|certification)\b", 1.5, "certification promo"),
    (r"\b(newsletter|subscribe|my channel|finally posted)\b", 1.5, "self-promotion"),
    (r"\b(i'?ve|i have) been (learning|taking|studying)\b", 1.0, "already a student"),
    (r"\bour online dance classroom\b|\bour classes\b", 2.0, "provider copy"),
]
READINESS_SIGNALS = [
    (r"\b(urgent|asap|immediately|soon|this (week|month)|next (week|month))\b", 0.4),
    (r"\b(budget|afford\w*|reasonable|fees?|price|cost|charges)\b", 0.3),
    (r"\b(timings?|schedule|time ?zone|slots?|weekends?|evenings?)\b", 0.25),
    (r"\b(demo|trial)\b", 0.25),
    (r"\b(enrol+|join|sign up|admission|register)\b", 0.3),
    (r"\blong time\b|\bfor a while\b", 0.3),
]
ONLINE_SIGNALS = r"\b(online|zoom|virtual|remote|skype|google meet|video call)\b"

# ---- Scoring -------------------------------------------------------------
WEIGHTS = {"interest": 0.40, "readiness": 0.25, "recency": 0.20, "location": 0.15}
RECENCY_HALF_LIFE_DAYS = 21
UNKNOWN_DATE_RECENCY = 0.30
HOT_MIN_SCORE = 0.65
HOT_MIN_READINESS = 0.25
WARM_MIN_SCORE = 0.40
DEFAULT_MAX_AGE_DAYS = 90

# ---- Learner Intent Cues ---------------------------------------------------
LEARNER_INTENT_CUES = [
    "enroll", "enrol", "admission", "do you teach", "do you offer classes",
    "do you take students", "how to join", "how can i join", "want to join",
    "fees", "fee structure", "batch timings", "demo class", "trial class",
    "please teach", "teach me", "i want to learn", "i would like to learn",
    "want to learn",
]
STRONG_CUES = [
    "enroll", "enrol", "admission", "do you teach", "do you offer classes",
    "how to join", "demo class", "fees",
]

# ---- Collection defaults ---------------------------------------------------
DEFAULT_YT_QUERIES = ["learn bharatanatyam online beginners", "bharatanatyam for adults beginners", "kathak online classes beginners", "learn indian classical dance online"]
DEFAULT_SUBREDDITS = ["ClassicalIndiandance"]  # add more communities you have checked and may use
DEFAULT_QUERIES = [
    "online bharatanatyam class", "learn bharatanatyam online", "online kathak class",
    "indian classical dance teacher online", "looking for dance classes classical",
]
