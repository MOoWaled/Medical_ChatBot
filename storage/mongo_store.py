"""
MongoDB storage layer for scraped NHS Inform conditions.
Handles connection, upsert, and batch operations.
"""

import logging
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ConnectionFailure, OperationFailure

from config import MONGO_URI, DB_NAME, COLLECTION_NAME

logger = logging.getLogger(__name__)


class MongoStore:
    """Manages MongoDB connection and document storage for conditions."""

    def __init__(self, uri: str = None, db_name: str = None, collection_name: str = None):
        self.uri = uri or MONGO_URI
        self.db_name = db_name or DB_NAME
        self.collection_name = collection_name or COLLECTION_NAME
        self.client = None
        self.db = None
        self.collection = None

    def connect(self) -> bool:
        """
        Establish MongoDB connection and set up the collection with indexes.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            # Force a connection attempt to verify it works
            self.client.admin.command("ping")

            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]

            # Create unique index on URL for upsert support
            self.collection.create_index("url", unique=True)

            logger.info(
                f"Connected to MongoDB: {self.uri} -> "
                f"{self.db_name}.{self.collection_name}"
            )
            return True

        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB at {self.uri}: {e}")
            return False
        except OperationFailure as e:
            logger.error(f"MongoDB operation failed: {e}")
            return False

    def store_condition(self, doc: dict) -> bool:
        """
        Upsert a single condition document by URL.
        If a document with the same URL exists, it gets updated.

        Args:
            doc: The condition dict to store.

        Returns:
            True if the operation succeeded.
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return False

        try:
            result = self.collection.update_one(
                {"url": doc["url"]},
                {"$set": doc},
                upsert=True,
            )
            if result.upserted_id:
                logger.debug(f"Inserted new: {doc.get('title', 'unknown')}")
            else:
                logger.debug(f"Updated existing: {doc.get('title', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"Failed to store {doc.get('title', 'unknown')}: {e}")
            return False

    def store_batch(self, docs: list[dict]) -> dict:
        """
        Bulk upsert a list of condition documents.

        Args:
            docs: List of condition dicts.

        Returns:
            Dict with counts: {"inserted": N, "updated": N, "errors": N}
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return {"inserted": 0, "updated": 0, "errors": len(docs)}

        operations = []
        for doc in docs:
            operations.append(
                UpdateOne(
                    {"url": doc["url"]},
                    {"$set": doc},
                    upsert=True,
                )
            )

        try:
            result = self.collection.bulk_write(operations, ordered=False)
            stats = {
                "inserted": result.upserted_count,
                "updated": result.modified_count,
                "errors": 0,
            }
            logger.info(
                f"Batch complete: {stats['inserted']} inserted, "
                f"{stats['updated']} updated"
            )
            return stats

        except Exception as e:
            logger.error(f"Batch store failed: {e}")
            return {"inserted": 0, "updated": 0, "errors": len(docs)}

    def condition_exists(self, url: str) -> bool:
        """Check if a condition URL already exists in the collection."""
        if self.collection is None:
            return False
        return self.collection.count_documents({"url": url.rstrip("/")}, limit=1) > 0

    def get_stats(self) -> dict:
        """Return basic stats about the collection."""
        if self.collection is None:
            return {"total": 0, "with_symptoms": 0, "with_causes": 0}

        total = self.collection.count_documents({})
        with_symptoms = self.collection.count_documents({"symptoms": {"$ne": None}})
        with_causes = self.collection.count_documents({"causes": {"$ne": None}})
        with_warnings = self.collection.count_documents({"warnings": {"$ne": None}})
        with_recs = self.collection.count_documents({"recommendations": {"$ne": None}})

        return {
            "total": total,
            "with_symptoms": with_symptoms,
            "with_causes": with_causes,
            "with_warnings": with_warnings,
            "with_recommendations": with_recs,
        }

    def close(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")
