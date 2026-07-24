import os
import json
import time
import requests
import pyrebase
from typing import Dict, Any, Optional, List
from .pyrestore import Pyrestore
from .storage import Storage

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

        self.storage_bucket = config.get("storageBucket")
        self.storage = Storage(
            project_id=self.project_id,
            storage_bucket=self.storage_bucket
        )

        # Session state
        self.user_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    # ---------------------------------------------------------
    # AUTHENTICATION METHODS
    # ---------------------------------------------------------

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Logs in a user. Returns True if successful, False otherwise."""
        if not email or not password:
            print("[Auth Error]: Missing email or password.")
            return {"status": "failure", "user_id": self.user_id, "token": self.access_token, "message": "Email and password are required."}

        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            refreshed = self.auth.refresh(user["refreshToken"])

            self.access_token = refreshed["idToken"]
            self.refresh_token = refreshed["refreshToken"]
            self.user_id = refreshed["userId"]

            # Authenticate Firestore automatically
            self.db.auth(self.access_token)

            print(f"[Success]: Logged in user '{self.user_id}'")
            return {"status": "success", "user_id": self.user_id, "token": self.access_token, "message": "Successful login"}

        except requests.exceptions.HTTPError as e:
            error_msg = self._parse_auth_error(e)
            #raise PermissionError(error_msg)
            return {"status": "failure","user_id": self.user_id, "token": self.access_token, "message": error_msg}

    def signup(
            self,
            email: str,
            password: str,
            required_fields: Optional[List[str]] = None,
            max_retries: int = 3,
            **user_data
    ) -> dict[str, Any]:
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
            raise ValueError("Email and password are required.")

        # Validate extra required fields before calling auth API
        if required_fields:
            missing = [f for f in required_fields if f not in user_data or user_data[f] is None or user_data[f] == ""]
            if missing:
                print(f"[Signup Error]: Missing required field(s): {', '.join(missing)}")
                return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"Missing required field(s): {', '.join(missing)}"
                }

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

                success = self._commit_with_retry(batch, max_retries=max_retries)
                if not success:
                    print("[Signup Error]: User created in Auth, but profile write failed after retries.")
                    return {
                        "status": "failure",
                        "user_id": self.user_id,
                        "token": self.access_token,
                        "message": "User created in Auth, but profile write failed after retries."
                        }

            print(f"[Success]: User signed up successfully with ID '{self.user_id}'")
            return {
                "status": "success",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"User signed up successfully with ID '{self.user_id}'"
                }

        except requests.exceptions.HTTPError as e:
            print(f"[Signup Failed]: {self._parse_auth_error(e)}")
            error_msg = self._parse_auth_error(e)
            raise PermissionError(error_msg)

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
            return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "No user_id logged in and no doc_id provided."
            }
        return self.db.child(collection).child(target_id).get()

    def set_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> dict[str, Any]:
        """Overwrites or creates a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Set Error]: No target doc_id provided and user is not logged in.")
            return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "No user_id logged in and no doc_id provided."
            }

        result = self.db.child(collection).child(target_id).set(data)
        if result is not None:
            print(f"[Success]: Document 'set' at {collection}/{target_id}")
            return {
                "status": "success",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"Document 'set' at {collection}/{target_id}"
            }
        return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "Document could not be created. Try again later."
            }

    def update_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> dict[str, Any]:
        """Updates specific fields in a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Update Error]: No target doc_id provided and user is not logged in.")
            return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "No user_id logged in and no doc_id provided."
            }

        result = self.db.child(collection).child(target_id).update(data)
        if result is not None:
            print(f"[Success]: Document 'updated' at {collection}/{target_id}")
            return {
                "status": "success",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"Document 'updated' at {collection}/{target_id}"
            }
        return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "Document could not be updated. Try again later."
            }

    def delete_document(self, collection: str, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """Deletes a document. Returns bool."""
        target_id = doc_id or self.user_id
        if not target_id:
            print("[Delete Error]: No target doc_id provided and user is not logged in.")
            return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "No user_id logged in and no doc_id provided."
            }

        success = self.db.child(collection).child(target_id).delete()
        if success:
            print(f"[Success]: Document 'deleted' at {collection}/{target_id}")
            return {
                "status": "success",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"Document 'deleted' at {collection}/{target_id}"
            }
        return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": "Document could not be deleted. Try again later."
            }

    def push_document(self, collection: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Adds a new document with an auto-generated ID to a collection."""
        result = self.db.child(collection).push(data)
        if result and "id" in result:
            print(f"[Success]: Pushed document to {collection} with generated ID '{result['id']}'")
            return result
        print(f"[Push Error]: Failed to push document to {collection}")
        return {
                "status": "failure",
                "user_id": self.user_id,
                "token": self.access_token,
                "message": f"Failed to push document to {collection}"
            }

    # ---------------------------------------------------------
    # SMART BATCH HELPERS
    # ---------------------------------------------------------

    def batch_update(self, collection: str, *doc_path_segments: str, max_retries: int = 3, **kwargs) -> Dict[str, Any]:
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
            raise ValueError("No document ID specified and no user logged in.")

        query = self.db.child(path_segments[0])
        for seg in path_segments[1:]:
            query = query.child(seg)

        batch = self.db.batch()
        batch.update(query, kwargs)

        return self._commit_with_retry(batch, max_retries=max_retries)

    def batch_multi_update(self, default_action: str = "update", max_retries: int = 3, **collections) -> Dict[str, Any]:
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
            raise ValueError("No collection updates specified.")

        valid_actions = {"update", "set", "delete"}
        batch = self.db.batch()

        for collection_name, doc_map in collections.items():
            if not isinstance(doc_map, dict):
                print(f"[Batch Error]: Value for collection '{collection_name}' must be a dict.")
                raise TypeError(f"Value for collection '{collection_name}' must be a dict.")

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
                    raise KeyError(f"Unsupported action '{doc_action}' for {collection_name}/{doc_id}")

                # Execute action on batch
                if doc_action == "set":
                    batch.set(query, payload)
                elif doc_action == "delete":
                    batch.delete(query)
                elif doc_action == "update":
                    batch.update(query, payload)

        return self._commit_with_retry(batch, max_retries=max_retries)

    # ---------------------------------------------------------
    # INTERNAL UTILITIES
    # ---------------------------------------------------------

    @staticmethod
    def _commit_with_retry(batch, max_retries: int = 3) -> Dict[str, Any]:
        """Commits a batch write with exponential backoff retries."""
        for attempt in range(1, max_retries + 1):
            if batch.commit():
                print(f"[Success]: Batch write committed (Attempt {attempt}).")
                return {"status": "success", "message": f"Batch write committed in {attempt} attempts.."}
            if attempt < max_retries:
                print(
                    f"[Batch Warning]: Commit failed (Attempt {attempt}/{max_retries}). Retrying in {0.5 * attempt}s...")
                time.sleep(0.5 * attempt)

        print(f"[Batch Error]: All {max_retries} commit attempts failed.")
        return {"status": "failure", "message": f"All {max_retries} commit attempts failed."}

    @staticmethod
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

    # ---------------------------------------------------------
    # STORAGE HELPERS (Defaults to current user_id)
    # ---------------------------------------------------------

    def upload_file(
            self,
            folder: str,
            local_file_path: str,
            filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [Sync] Uploads a local file to Firebase Storage.
        If filename is omitted, defaults to current user_id + original extension.

        Example:
            fb.upload_file("avatars", "path/to/my_photo.png")
            # Uploads to: avatars/{user_id}.png
        """
        target_name = filename or self._get_default_filename(local_file_path)
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        result = self.storage.child(folder).child(target_name).put(local_file_path)
        if result:
            url = self.storage.child(folder).child(target_name).get_url()
            print(f"[Success]: File uploaded to {folder}/{target_name}")
            return {
                "status": "success",
                "path": f"{folder}/{target_name}",
                "url": url,
                "metadata": result
            }

        return {"status": "failure", "message": f"Failed to upload file to {folder}/{target_name}"}

    def download_file(
            self,
            folder: str,
            destination_path: str,
            filename: Optional[str] = None
    ) -> bool:
        """
        [Sync] Downloads a file from Storage to a local path.
        Defaults to searching for a file named after the logged-in user_id if filename is omitted.
        """
        target_name = filename or self.user_id
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        success = self.storage.child(folder).child(target_name).download(destination_path)
        if success:
            print(f"[Success]: Downloaded {folder}/{target_name} to {destination_path}")
            return True
        return False

    def get_file_url(self, folder: str, filename: Optional[str] = None) -> Optional[str]:
        """
        [Sync] Fetches the public/authenticated download URL for a file in Storage.
        Defaults to logged-in user_id if filename is omitted.
        """
        target_name = filename or self.user_id
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        return self.storage.child(folder).child(target_name).get_url()

    def delete_file(self, folder: str, filename: Optional[str] = None) -> bool:
        """
        [Sync] Deletes a file from Storage.
        Defaults to logged-in user_id if filename is omitted.
        """
        target_name = filename or self.user_id
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        return self.storage.child(folder).child(target_name).delete()

    # ---------------------------------------------------------
    # ASYNC STORAGE HELPERS (For Flet or Async code)
    # ---------------------------------------------------------

    async def upload_file_async(
            self,
            folder: str,
            local_file_path: str,
            filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """[Async] Non-blocking upload helper for Flet and asyncio apps."""
        target_name = filename or self._get_default_filename(local_file_path)
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        result = await self.storage.child(folder).child(target_name).put_async(local_file_path)
        if result:
            url = await self.storage.child(folder).child(target_name).get_url_async()
            print(f"[Success]: Async uploaded file to {folder}/{target_name}")
            return {
                "status": "success",
                "path": f"{folder}/{target_name}",
                "url": url,
                "metadata": result
            }

        return {"status": "failure", "message": f"Failed to async upload file to {folder}/{target_name}"}

    async def download_file_async(
            self,
            folder: str,
            destination_path: str,
            filename: Optional[str] = None
    ) -> bool:
        """[Async] Non-blocking download helper."""
        target_name = filename or self.user_id
        if not target_name:
            print("[Storage Error]: No filename provided and no user logged in.")
            raise ValueError("No user_id logged in and no filename provided.")

        return await self.storage.child(folder).child(target_name).download_async(destination_path)

    # ---------------------------------------------------------
    # INTERNAL STORAGE UTILITIES
    # ---------------------------------------------------------

    def _get_default_filename(self, local_file_path: str) -> Optional[str]:
        """Generates default filename (user_id + local file extension)."""
        if not self.user_id:
            return None
        _, ext = os.path.splitext(local_file_path)
        return f"{self.user_id}{ext}"