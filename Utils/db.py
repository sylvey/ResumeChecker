"""MongoDB handle for annotation storage.
 
One document per resume-section x JD-section pair -- the grain the embedding
model will train on, so no unpacking step later.
"""
 
import os
 
from pymongo import ASCENDING, MongoClient
 
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB", "resumechecker")
 
 
def get_db():
    """Connect and ensure indexes. Called once at startup."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
 
    # Re-scoring the same resume/JD pair should overwrite cleanly rather than
    # silently accumulating duplicate training rows.
    db.annotations.create_index(
        [
            ("resume_id", ASCENDING),
            ("jd_id", ASCENDING),
            ("resume_section_name", ASCENDING),
            ("jd_section_name", ASCENDING),
        ],
        name="pair_identity",
    )
    # The training exporter reads by source (llm vs human) and by score band.
    db.annotations.create_index([("source", ASCENDING)], name="by_source")
    db.annotations.create_index([("matching_score", ASCENDING)], name="by_score")
    return db