# Bias hint for the curation/summarization prompts — NOT a hard filter.
# The LLM makes the actual judgment call on what counts as security/war news.
SECURITY_WAR_KEYWORDS = [
    "ביטחון", "מלחמה", "צה\"ל", "צהל", "פיגוע", "טיל", "רקטות", "רקטה",
    "חיזבאללה", "חמאס", "עזה", "לבנון", "איראן", "גיוס", "מילואים",
    "נפגעים", "הרוגים", "פצועים", "אזעקה", "אזעקות", "כיפת ברזל",
    "חטופים", "שבויים", "גבול", "התקפה", "תקיפה", "חדירה",
]
