import httpx
import urllib.parse
import datetime
import base64
from typing import Any


# =====================================================================
# 1. FIELD TRANSFORMS (Atomic server-side operations)
# =====================================================================

class FieldValue:
    """Special values used to transform fields directly on the server."""

    def __init__(self, transform_type, value=None):
        self.transform_type = transform_type
        self.value = value

    @staticmethod
    def increment(n):
        return FieldValue("increment", n)

    @staticmethod
    def server_timestamp():
        return FieldValue("server_timestamp")

    @staticmethod
    def array_union(elements):
        return FieldValue("array_union", elements if isinstance(elements, list) else [elements])

    @staticmethod
    def array_remove(elements):
        return FieldValue("array_remove", elements if isinstance(elements, list) else [elements])


# =====================================================================
# 2. QUERY BUILDER (Advanced Filtering & Sorting)
# =====================================================================

class FirestoreQuery:
    """Handles path chaining, querying, and execution."""

    OPERATOR_MAP = {
        "==": "EQUAL",
        "!=": "NOT_EQUAL",
        "<": "LESS_THAN",
        "<=": "LESS_THAN_OR_EQUAL",
        ">": "GREATER_THAN",
        ">=": "GREATER_THAN_OR_EQUAL",
        "array-contains": "ARRAY_CONTAINS",
        "in": "IN",
        "array-contains-any": "ARRAY_CONTAINS_ANY"
    }

    def __init__(self, base_url, token=None, path=""):
        self.base_url = base_url
        self.token = token
        self.path = path

        # Query parameters
        self._where_filters = []
        self._order_by = []
        self._limit_val = None

    def child(self, path_segment):
        new_path = f"{self.path}/{path_segment}" if self.path else str(path_segment)
        return FirestoreQuery(self.base_url, self.token, new_path)

    def _get_headers(self):
        if not self.token:
            raise ValueError("Authentication token is missing. Call db.auth(id_token) first.")
        return {"Authorization": f"Bearer {self.token}"}

    # ------------------ Query Chaining Methods ------------------

    def where(self, field, op, value):
        if op not in self.OPERATOR_MAP:
            raise ValueError(f"Unsupported operator '{op}'. Supported: {list(self.OPERATOR_MAP.keys())}")
        self._where_filters.append({
            "fieldFilter": {
                "field": {"fieldPath": field},
                "op": self.OPERATOR_MAP[op],
                "value": self._to_firestore_value(value)
            }
        })
        return self

    def order_by(self, field, direction="ASCENDING"):
        direction_upper = direction.upper()
        if direction_upper in ["ASC", "ASCENDING"]:
            dir_enum = "ASCENDING"
        elif direction_upper in ["DESC", "DESCENDING"]:
            dir_enum = "DESCENDING"
        else:
            raise ValueError("Direction must be 'ASC' or 'DESC'")

        self._order_by.append({
            "field": {"fieldPath": field},
            "direction": dir_enum
        })
        return self

    def limit(self, count):
        self._limit_val = count
        return self

    # ------------------ Execution Methods ------------------

    def get(self):
        headers = self._get_headers()

        # IF QUERY FILTERS OR LIMITS WERE ADDED: Use :runQuery endpoint
        if self._where_filters or self._order_by or self._limit_val:
            # The collection ID is the last path segment
            collection_id = self.path.split("/")[-1]
            # Parent path is everything before the collection ID
            parent_segments = self.path.split("/")[:-1]
            parent_path = f"/{'/'.join(parent_segments)}" if parent_segments else ""

            url = f"{self.base_url}{parent_path}:runQuery"

            structured_query: dict[str, Any] = {
                "from": [{"collectionId": collection_id}]
            }

            # Build 'where' clause
            if len(self._where_filters) == 1:
                structured_query["where"] = self._where_filters[0]
            elif len(self._where_filters) > 1:
                structured_query["where"] = {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": self._where_filters
                    }
                }

            if self._order_by:
                structured_query["orderBy"] = self._order_by

            if self._limit_val:
                structured_query["limit"] = self._limit_val

            response = httpx.post(url, headers=headers, json={"structuredQuery": structured_query})

            if response.status_code == 200:
                results = response.json()
                parsed_docs = []
                for item in results:
                    if "document" in item:
                        parsed_docs.append(self._parse_single_doc(item["document"]))
                return parsed_docs
            else:
                print(f"Query Error {response.status_code}: {response.text}")
                return []

        # STANDARD GET (Single Document or Entire Collection)
        else:
            url = f"{self.base_url}/{self.path}"
            response = httpx.get(url, headers=headers)

            if response.status_code == 200:
                return self._parse_firestore_doc(response.json())
            print(f"Error {response.status_code}: {response.text}")
            return None

    def set(self, data_dict):
        url = f"{self.base_url}/{self.path}"
        payload = self.build_firestore_payload(data_dict)
        response = httpx.patch(url, headers=self._get_headers(), json=payload)

        if response.status_code == 200:
            return self._parse_firestore_doc(response.json())
        print(f"Error {response.status_code}: {response.text}")
        return None

    def update(self, data_dict):
        mask_params = [f"updateMask.fieldPaths={urllib.parse.quote(k)}" for k in data_dict.keys()]
        url = f"{self.base_url}/{self.path}?{'&'.join(mask_params)}"
        payload = self.build_firestore_payload(data_dict)
        response = httpx.patch(url, headers=self._get_headers(), json=payload)

        if response.status_code == 200:
            return self._parse_firestore_doc(response.json())
        print(f"Error {response.status_code}: {response.text}")
        return None

    def push(self, data_dict):
        url = f"{self.base_url}/{self.path}"
        payload = self.build_firestore_payload(data_dict)
        response = httpx.post(url, headers=self._get_headers(), json=payload)

        if response.status_code == 200:
            return self._parse_firestore_doc(response.json())
        print(f"Error {response.status_code}: {response.text}")
        return None

    def delete(self):
        url = f"{self.base_url}/{self.path}"
        response = httpx.delete(url, headers=self._get_headers())
        return response.status_code == 200

    # ------------------ Serialization Engine ------------------

    def _to_firestore_value(self, value):
        if isinstance(value, FieldValue):
            # Special handling if a FieldValue was passed into standard serialization
            if value.transform_type == "increment":
                return {"integerValue": str(value.value)}
            elif value.transform_type == "server_timestamp":
                return {
                    "timestampValue": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")}

        if isinstance(value, bool):
            return {"booleanValue": value}
        elif isinstance(value, int):
            return {"integerValue": str(value)}
        elif isinstance(value, float):
            return {"doubleValue": value}
        elif value is None:
            return {"nullValue": None}
        elif isinstance(value, datetime.datetime):
            formatted_time = value.isoformat() + "Z" if value.tzinfo is None else value.astimezone(
                datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            return {"timestampValue": formatted_time}
        elif isinstance(value, bytes):
            return {"bytesValue": base64.b64encode(value).decode('utf-8')}
        elif isinstance(value, list):
            return {"arrayValue": {"values": [self._to_firestore_value(v) for v in value]}}
        elif isinstance(value, dict):
            return {"mapValue": {"fields": {k: self._to_firestore_value(v) for k, v in value.items()}}}
        else:
            return {"stringValue": str(value)}

    def _from_firestore_value(self, value_dict):
        if not value_dict: return None
        type_key = list(value_dict.keys())[0]
        raw_value = value_dict[type_key]

        if type_key == "stringValue":
            return str(raw_value)
        elif type_key == "integerValue":
            return int(raw_value)
        elif type_key == "doubleValue":
            return float(raw_value)
        elif type_key == "booleanValue":
            return bool(raw_value)
        elif type_key == "nullValue":
            return None
        elif type_key == "timestampValue":
            return datetime.datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        elif type_key == "bytesValue":
            return base64.b64decode(raw_value)
        elif type_key == "arrayValue":
            return [self._from_firestore_value(v) for v in raw_value.get("values", [])]
        elif type_key == "mapValue":
            return {k: self._from_firestore_value(v) for k, v in raw_value.get("fields", {}).items()}
        return raw_value

    def _parse_firestore_doc(self, doc_json):
        if "documents" in doc_json:
            return [self._parse_single_doc(doc) for doc in doc_json["documents"]]
        elif "fields" in doc_json:
            return self._parse_single_doc(doc_json)
        return None

    def _parse_single_doc(self, doc):
        data = {}
        if "name" in doc:
            data["id"] = doc["name"].split("/")[-1]
        if "fields" not in doc: return data
        for key, value_dict in doc["fields"].items():
            data[key] = self._from_firestore_value(value_dict)
        return data

    def build_firestore_payload(self, data_dict):
        return {"fields": {k: self._to_firestore_value(v) for k, v in data_dict.items()}}


# =====================================================================
# 3. BATCH WRITES (Atomic multi-document transactions)
# =====================================================================

class Batch:
    """Queues operations to commit them atomically."""

    def __init__(self, db):
        self.db = db
        self.writes = []

    def set(self, query_obj, data_dict):
        doc_path = f"{self.db.base_url}/{query_obj.path}"
        payload = query_obj.build_firestore_payload(data_dict)
        self.writes.append({"update": {"name": doc_path, **payload}})
        return self

    def update(self, query_obj, data_dict):
        doc_path = f"{self.db.base_url}/{query_obj.path}"
        payload = query_obj.build_firestore_payload(data_dict)
        mask = {"fieldPaths": list(data_dict.keys())}
        self.writes.append({"update": {"name": doc_path, **payload}, "updateMask": mask})
        return self

    def delete(self, query_obj):
        doc_path = f"{self.db.base_url}/{query_obj.path}"
        self.writes.append({"delete": doc_path})
        return self

    def commit(self):
        """Executes all queued writes atomically in a single network request."""
        # Split project database root path
        parent_db_url = self.db.base_url.rsplit("/documents", 1)[0]
        url = f"{parent_db_url}:commit"

        headers = {"Authorization": f"Bearer {self.db.token}"}
        payload = {"writes": self.writes}

        response = httpx.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            self.writes = []  # Reset queue
            return True
        else:
            print(f"Batch Commit Error {response.status_code}: {response.text}")
            return False


# =====================================================================
# 4. MAIN ENTRY POINT
# =====================================================================

class Pyrestore:
    """The main initialization class for Pyrestore."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"
        self.token = None

    def auth(self, id_token):
        self.token = id_token

    def child(self, path_segment):
        return FirestoreQuery(self.base_url, self.token).child(path_segment)

    def batch(self):
        """Creates a new Batch transaction instance."""
        if not self.token:
            raise ValueError("Authentication token is missing. Call db.auth(id_token) first.")
        return Batch(self)