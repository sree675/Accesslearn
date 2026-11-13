"""Shared vocabulary used by the API, the recommender and the frontend."""

NEEDS = ["captions", "audio_description", "screen_reader", "low_motion", "simple_language"]

NEED_LABELS = {
    "captions": "Captions or transcript",
    "audio_description": "Audio description",
    "screen_reader": "Screen-reader friendly",
    "low_motion": "Low motion / calm pace",
    "simple_language": "Simple language",
}

FORMATS = ["video", "audio", "text", "interactive"]
LEVELS = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
PACES = ["Slow", "Medium", "Fast"]

# Suggested hard accessibility needs when a student selects a disability.
DISABILITY_PRESETS = {
    "Visual impairment": {"audio_description": True, "screen_reader": True},
    "Hearing impairment": {"captions": True},
    "Dyslexia": {"simple_language": True},
    "Cognitive or learning disability": {"simple_language": True},
    "ADHD": {},
    "Autism spectrum": {},
    "Motor impairment": {},
    "None": {},
}

# Softer preferences the recommender rewards but never enforces.
DISABILITY_SOFT_PREFS = {
    "ADHD": ["short", "low_motion"],
    "Autism spectrum": ["low_motion", "simple_language"],
    "Cognitive or learning disability": ["short", "simple_language"],
    "Dyslexia": ["simple_language"],
}

TOPICS = {
    "Maths": ["Fractions", "Algebra Basics", "Geometry Shapes", "Percentages"],
    "Science": ["Photosynthesis", "States of Matter", "Human Body Systems", "Electricity Basics"],
    "English": ["Parts of Speech", "Reading Comprehension", "Essay Writing", "Grammar Tenses"],
    "Computer Science": ["Intro to Programming", "Binary Numbers", "Internet Safety", "Algorithms"],
    "Social Studies": ["Indian Constitution", "Climate and Weather", "Map Skills", "Ancient Civilizations"],
    "Life Skills": ["Money Management", "Time Management", "Communication Skills", "Healthy Habits"],
}
SUBJECTS = list(TOPICS.keys())
SHORT_MINUTES = 8
