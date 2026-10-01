"""
Storage layer for SmartHire.

Uses MongoDB when MONGODB_URI is set and reachable, otherwise falls back to
JSON files in data/ and PDFs in resumes/. Both backends expose the same small
interface so the Flask app never has to care which one is active.
"""

import base64
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Serverless hosts (Vercel) only allow writing to /tmp, which is wiped between
# invocations, so the JSON fallback there is for smoke tests only: set MONGODB_URI.
_WRITABLE_ROOT = "/tmp/smarthire" if os.getenv("VERCEL") else PROJECT_ROOT
DATA_DIR = os.path.join(_WRITABLE_ROOT, "data")
UPLOAD_DIR = os.path.join(_WRITABLE_ROOT, "resumes")

# Large or internal fields that should never be sent to the frontend
HIDDEN_FIELDS = {"_id", "file_content"}


def _clean(doc):
    return {k: v for k, v in doc.items() if k not in HIDDEN_FIELDS}


class JsonCollection:
    """A list of documents stored in one JSON file, keyed by a unique field."""

    def __init__(self, filename, key):
        self.path = os.path.join(DATA_DIR, filename)
        self.key = key
        self.lock = threading.Lock()
        os.makedirs(DATA_DIR, exist_ok=True)

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, docs):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2, default=str)
        os.replace(tmp, self.path)

    def all(self):
        with self.lock:
            return [_clean(d) for d in self._read()]

    def get(self, key_value):
        with self.lock:
            for d in self._read():
                if d.get(self.key) == key_value:
                    return d
        return None

    def upsert(self, doc):
        with self.lock:
            docs = self._read()
            for i, d in enumerate(docs):
                if d.get(self.key) == doc[self.key]:
                    docs[i] = doc
                    break
            else:
                docs.append(doc)
            self._write(docs)

    def update(self, key_value, fields):
        with self.lock:
            docs = self._read()
            for d in docs:
                if d.get(self.key) == key_value:
                    d.update(fields)
                    self._write(docs)
                    return True
        return False

    def delete(self, key_value):
        with self.lock:
            docs = self._read()
            kept = [d for d in docs if d.get(self.key) != key_value]
            if len(kept) == len(docs):
                return False
            self._write(kept)
            return True


class MongoCollection:
    def __init__(self, collection, key):
        self.col = collection
        self.key = key

    def all(self):
        return list(self.col.find({}, {"_id": 0, "file_content": 0}))

    def get(self, key_value):
        return self.col.find_one({self.key: key_value}, {"_id": 0})

    def upsert(self, doc):
        self.col.replace_one({self.key: doc[self.key]}, doc, upsert=True)

    def update(self, key_value, fields):
        return self.col.update_one({self.key: key_value}, {"$set": fields}).matched_count > 0

    def delete(self, key_value):
        return self.col.delete_one({self.key: key_value}).deleted_count > 0


class Storage:
    def __init__(self):
        self.backend = "json"
        self.db = None
        uri = os.getenv("MONGODB_URI")
        if uri:
            try:
                from pymongo import MongoClient
                client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")
                self.db = client["smarthire"]
                self.backend = "mongodb"
                logger.info("Connected to MongoDB")
            except Exception as e:
                logger.warning(f"MongoDB unavailable, using JSON files instead: {e}")

        if self.db is not None:
            self.jobs = MongoCollection(self.db["jobs"], "id")
            self.resumes = MongoCollection(self.db["resumes"], "email")
        else:
            self.jobs = JsonCollection("jobs.json", "id")
            self.resumes = JsonCollection("resumes.json", "email")
            os.makedirs(UPLOAD_DIR, exist_ok=True)

    # PDFs live in MongoDB when available so they survive redeploys on hosts
    # with ephemeral disks (Render, Railway). Otherwise they go to resumes/.
    def save_file(self, file_id, data):
        if self.db is not None:
            self.db["resume_files"].replace_one(
                {"file_id": file_id}, {"file_id": file_id, "data": data}, upsert=True
            )
        else:
            with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f:
                f.write(data)

    def load_file(self, resume):
        file_id = resume.get("file_id")
        if file_id and self.db is not None:
            doc = self.db["resume_files"].find_one({"file_id": file_id})
            if doc:
                return bytes(doc["data"])
        if file_id:
            path = os.path.join(UPLOAD_DIR, file_id)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
        # Resumes uploaded by older versions stored the PDF as base64
        if resume.get("file_content"):
            return base64.b64decode(resume["file_content"])
        return None

    def delete_file(self, file_id):
        if not file_id:
            return
        if self.db is not None:
            self.db["resume_files"].delete_one({"file_id": file_id})
        path = os.path.join(UPLOAD_DIR, file_id)
        if os.path.isfile(path):
            os.remove(path)
