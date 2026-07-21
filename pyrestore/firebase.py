import json
import time
import requests
import pyrebase
from typing import Dict, Any, Optional, List
from pyrestore.pyrestore import Pyrestore

# ---------------------------------------------------------
# INTERNAL UTILITIES
# ---------------------------------------------------------

def _commit_with_retry(batch, max_retries: int = 3) -> bool:
    """Commits a batch write with exponential backoff retries."""
    for attempt in range(1, max_retries + 1):
        if batch.commit():
            print(f"[Success]: Batch write committed (Attempt {attempt}).")
            return True
        if attempt < max_retries:
            print(
                f"[Batch Warning]: Commit failed (Attempt {attempt}/{max_retries}). Retrying in {0.5 * attempt}s...")
            time.sleep(0.5 * attempt)

    print(f"[Batch Error]: All {max_retries} commit attempts failed.")
    return False

def _parse_auth_error(e: requests.exceptions.HTTPError) -> str:
    try:
        err = json.loads(e.args[1])
        code = err["error"]["message"]
        error_map = {
            "INVALID_EMAIL": "Please enter a valid email address.",
            "INVALID_PASSWORD": "Please enter a valid password.",
            "EMAIL_NOT_FOUND": "Could not find an account with that email address.",
            "USER_NOT_FOUND": "Could not find an account with that email address.",
            "WRONG_PASSWORD": "Incorrect password.",
            "EMAIL_EXISTS": "An account with this email already exists."
        }
        return error_map.get(code, f"Authentication error: {code}")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return "An unknown error occurred during authentication."


class FirebaseManager:
    """A simplified, beginner-friendly Firebase Manager for Authentication and Firestore."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.project_id = config.get("projectId")
        if not self.project_id:
            raise ValueError("Firebase configuration dictionary must contain 'projectId'.")

        self.firebase = pyrebase.initialize_app(self.config)
        self.db = Pyrestore(self.project_id)
        self.auth = self.firebase.auth()

        # Session state
        self.user_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    # ---------------------------------------------------------
    # AUTHENTICATION METHODS
    # ---------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        """Logs in a user. Returns True if successful, False otherwise."""
        if not email or not password:
            print("[Auth Error]: Missing email or password.")
            return False

        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            refreshed = self.auth.refresh(user["refreshToken"])

            self.access_token = refreshed["idToken"]
            self.refresh_token = refreshed["refreshToken"]
            self.user_id = refreshed["userId"]

            # Authenticate Firestore automatically
            self.db.auth(self.access_token)

            print(f"[Success]: Logged in user '{self.user_id}'")
            return True

        except requests.exceptions.HTTPError as e:
            print(f"[Auth Failed]: {_parse_auth_error(e)}")
            return False
        except Exception as e:
            print(f"[Auth Error]: {e}")
            return False

    def signup(
            self,
            email: str,
            password: str,
            required_fields: Optional[List[str]] = None,
            max_retries: int = 3,
            **user_data
    ) -> bool:
        """
        Creates a user account and writes profile data atomically.

        :param email: User email
        :param password: User password
        :param required_fields: List of keys that must be present in user_data (e.g. ['fname', 'lname', 'role'])
        :param max_retries: Number of batch commit retry attempts if network fails
        :param user_data: Extra profile key-value pairs (fname="John", lname="Doe", etc.)
        """
        if not email or not password:
            print("[Signup Error]: Email and password are required.")
            return False

        # Validate extra required fields before calling auth API
        if required_fields:
            missing = [f for f in required_fields if f not in user_data or user_data[f] is None or user_data[f] == ""]
            if missing:
                print(f"[Signup Error]: Missing required field(s): {', '.join(missing)}")
                return False

        try:
            # 1. Create auth user
            user = self.auth.create_user_with_email_and_password(email, password)
            self.auth.send_email_confirmation(user["idToken"])

            # 2. Refresh tokens
            refreshed = self.auth.refresh(user["refreshToken"])
            self.access_token = refreshed["idToken"]
            self.refresh_token = refreshed["refreshToken"]
            self.user_id = refreshed["localId"]

            self.db.auth(self.access_token)

            # 3. Save profile data using an atomic batch with retry logic
            if user_data:
                profile_payload = {"email": email, **user_data}

                batch = self.db.batch()
                batch.set(self.db.child("users").child(self.user_id), profile_payload)

                success = _commit_with_retry(batch, max_retries=max_retries)
                if not success:
                    print("[Signup Error]: User created in Auth, but profile write failed after retries.")
                    return False

            print(f"[Success]: User signed up successfully with ID '{self.user_id}'")
            return True

        except requests.exceptions.HTTPError as e:
            print(f"[Signup Failed]: {_parse_auth_error(e)}")
            return False
        except Exception as e:
            print(f"[Signup Error]: {e}")
            return False

    def refresh_session(self, refresh_token: str) -> bool:
        """Refreshes expired access tokens. Returns bool."""
        try:
            refreshed = self.auth.refresh(refresh_token)
            self.user_id = refreshed["userId"]
            self.access_token = refreshed["idToken"]
            self.db.auth(self.access_token)
            print("[Success]: Tokens refreshed.")
            return True
        except Exception as e:
            print(f"[Token Refresh Failed]: {e}")
            return False

    # ---------------------------------------------------------
    # FIRESTORE CRUD HELPERS
    # ---------------------------------------------------------

    def get_document(self, collection: str, doc_id: Optional[str] = None) -> Any:
        """Fetches a document dictionary. Defaults to current user_id."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Get Error]: No target doc_id provided and user is not logged in.")
            return None
        return self.db.child(collection).child(target_id).get()

    def set_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> bool:
        """Overwrites or creates a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Set Error]: No target doc_id provided and user is not logged in.")
            return False

        result = self.db.child(collection).child(target_id).set(data)
        if result is not None:
            print(f"[Success]: Document 'set' at {collection}/{target_id}")
            return True
        return False

    def update_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> bool:
        """Updates specific fields in a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Update Error]: No target doc_id provided and user is not logged in.")
            return False

        result = self.db.child(collection).child(target_id).update(data)
        if result is not None:
            print(f"[Success]: Document 'updated' at {collection}/{target_id}")
            return True
        return False

    def delete_document(self, collection: str, doc_id: Optional[str] = None) -> bool:
        """Deletes a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Delete Error]: No target doc_id provided and user is not logged in.")
            return False

        success = self.db.child(collection).child(target_id).delete()
        if success:
            print(f"[Success]: Document 'deleted' at {collection}/{target_id}")
            return True
        return False

    def push_document(self, collection: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Adds a new document with an auto-generated ID to a collection."""
        result = self.db.child(collection).push(data)
        if result and "id" in result:
            print(f"[Success]: Pushed document to {collection} with generated ID '{result['id']}'")
            return result
        print(f"[Push Error]: Failed to push document to {collection}")
        return None

    # ---------------------------------------------------------
    # SMART BATCH HELPERS
    # ---------------------------------------------------------

    def batch_update(self, collection: str, *doc_path_segments: str, max_retries: int = 3, **kwargs) -> bool:
        """
        Executes an atomic batch update on a single document path.

        Example (Logged-in User):
            fb.batch_update("users", role="parent", age=36)

        Example (Custom Path):
            fb.batch_update("families", "family_123", familyName="Smith", members=4)
        """
        if doc_path_segments:
            path_segments = [collection] + list(doc_path_segments)
        elif self.user_id:
            path_segments = [collection, self.user_id]
        else:
            print("[Batch Error]: No document ID specified and no user logged in.")
            return False

        query = self.db.child(path_segments[0])
        for seg in path_segments[1:]:
            query = query.child(seg)

        batch = self.db.batch()
        batch.update(query, kwargs)

        return _commit_with_retry(batch, max_retries=max_retries)

    def batch_multi_update(self, default_action: str = "update", max_retries: int = 3, **collections) -> bool:
        """
        Executes an atomic batch write across multiple collections.

        Supports both global actions and per-document explicit actions ("set", "update", "delete").

        :param default_action: Default action ("update", "set", "delete") if not specified per document.
        :param max_retries: Number of retry attempts on network failure.
        :param collections: Collection mappings where value is {doc_id: payload_dict_or_action_dict}

        Example with Mixed Actions:
            fb.batch_multi_update(
                users={
                    user_id: {"_action": "set", "data": {"name": "Morty", "email": "morty@example.com"}}
                },
                families={
                    family_id: {"members_count": 5}  # Uses default_action ("update")
                },
                invites={
                    invite_id: {"_action": "delete"} # Deletes document
                }
            )
        """
        if not collections:
            print("[Batch Error]: No collection updates specified.")
            return False

        valid_actions = {"update", "set", "delete"}
        batch = self.db.batch()

        for collection_name, doc_map in collections.items():
            if not isinstance(doc_map, dict):
                print(f"[Batch Error]: Value for collection '{collection_name}' must be a dict.")
                return False

            for doc_id, item_data in doc_map.items():
                query = self.db.child(collection_name).child(doc_id)

                # Check if this document explicitly defines its own action
                if isinstance(item_data, dict) and "_action" in item_data:
                    doc_action = item_data.get("_action", default_action)
                    payload = item_data.get("data", {})
                else:
                    doc_action = default_action
                    payload = item_data

                if doc_action not in valid_actions:
                    print(f"[Batch Error]: Unsupported action '{doc_action}' for {collection_name}/{doc_id}.")
                    return False

                # Execute action on batch
                if doc_action == "set":
                    batch.set(query, payload)
                elif doc_action == "delete":
                    batch.delete(query)
                elif doc_action == "update":
                    batch.update(query, payload)

        return _commit_with_retry(batch, max_retries=max_retries)