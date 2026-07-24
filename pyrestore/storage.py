import os
import httpx
import mimetypes
from typing import Optional, Dict, Any

class Storage:
    """
    An httpx-backed Google Cloud Storage client supporting both
    synchronous and asynchronous operations.
    """

    def __init__(self, project_id: str, storage_bucket: Optional[str] = None, auth_token: Optional[str] = None):
        self.project_id = project_id

        # Format storage bucket URL (e.g., "your-app.appspot.com" or "your-app.firebasestorage.app")
        bucket = storage_bucket or f"{project_id}.appspot.com"
        self.bucket = bucket.replace("gs://", "").strip("/")

        self.token: Optional[str] = auth_token
        self.path_segments: list[str] = []

    def auth(self, token: str) -> "Storage":
        """Sets or updates the Auth ID token for Storage requests."""
        self.token = token
        return self

    def child(self, *paths: str) -> "Storage":
        """Chainably builds object paths inside Firebase Storage (e.g., storage.child('images').child('avatar.jpg'))."""
        new_instance = Storage(self.project_id, self.bucket, self.token)
        new_instance.path_segments = self.path_segments.copy()

        for p in paths:
            cleaned = p.strip("/")
            if cleaned:
                new_instance.path_segments.append(cleaned)

        return new_instance

    @property
    def object_path(self) -> str:
        """Returns the unencoded full file path in Storage."""
        return "/".join(self.path_segments)

    @property
    def _encoded_path(self) -> str:
        """Encodes path slashes as %2F for GCP Firebase Storage REST API compliance."""
        return "%2F".join(self.path_segments)

    def _get_api_url(self) -> str:
        """Constructs the base GCP Storage REST URL for this object."""
        return f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o/{self._encoded_path}"

    def _get_headers(self) -> Dict[str, str]:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # =========================================================
    # REGION: SYNCHRONOUS METHODS
    # =========================================================

    def put(self, local_file_path: str) -> Optional[Dict[str, Any]]:
        """
        [Sync] Uploads a local file to Firebase Storage.
        Returns metadata dictionary including download URL parameters on success.
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"Local file not found at '{local_file_path}'")

        content_type, _ = mimetypes.guess_type(local_file_path)
        headers = self._get_headers()
        headers["Content-Type"] = content_type or "application/octet-stream"

        url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o?name={self._encoded_path}"

        with open(local_file_path, "rb") as file_data:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, content=file_data.read())

                if response.status_code == 200:
                    print(f"[Success]: File uploaded synchronous to '{self.object_path}'")
                    return response.json()

                print(f"[Storage Error]: Upload failed ({response.status_code}): {response.text}")
                return None

    def get_url(self) -> Optional[str]:
        """[Sync] Retrieves the public/authenticated download URL for a file in Storage."""
        url = self._get_api_url()
        with httpx.Client() as client:
            response = client.get(url, headers=self._get_headers())

            if response.status_code == 200:
                data = response.json()
                download_tokens = data.get("downloadTokens")
                if download_tokens:
                    return f"{url}?alt=media&token={download_tokens}"
                return f"{url}?alt=media"

            print(f"[Storage Error]: Failed to get URL ({response.status_code}): {response.text}")
            return None

    def download(self, destination_path: str) -> bool:
        """[Sync] Downloads a file from Storage and saves it locally."""
        download_url = self.get_url()
        if not download_url:
            return False

        with httpx.Client() as client:
            response = client.get(download_url)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
                with open(destination_path, "wb") as f:
                    f.write(response.content)
                print(f"[Success]: File downloaded to '{destination_path}'")
                return True

            print(f"[Storage Error]: Download failed ({response.status_code})")
            return False

    def delete(self) -> bool:
        """[Sync] Deletes a file from Firebase Storage."""
        url = self._get_api_url()
        with httpx.Client() as client:
            response = client.delete(url, headers=self._get_headers())
            if response.status_code == 204:
                print(f"[Success]: File '{self.object_path}' deleted from Storage.")
                return True

            print(f"[Storage Error]: Delete failed ({response.status_code}): {response.text}")
            return False

    # =========================================================
    # REGION: ASYNCHRONOUS METHODS
    # =========================================================

    async def put_async(self, local_file_path: str) -> Optional[Dict[str, Any]]:
        """
        [Async] Uploads a local file to Firebase Storage asynchronously.
        Ideal for non-blocking operations in UI frameworks (Flet) or FastAPI.
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"Local file not found at '{local_file_path}'")

        content_type, _ = mimetypes.guess_type(local_file_path)
        headers = self._get_headers()
        headers["Content-Type"] = content_type or "application/octet-stream"

        url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o?name={self._encoded_path}"

        with open(local_file_path, "rb") as file_data:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, content=file_data.read())

                if response.status_code == 200:
                    print(f"[Success]: File uploaded async to '{self.object_path}'")
                    return response.json()

                print(f"[Storage Error]: Async upload failed ({response.status_code}): {response.text}")
                return None

    async def get_url_async(self) -> Optional[str]:
        """[Async] Retrieves the download URL for a file asynchronously."""
        url = self._get_api_url()
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())

            if response.status_code == 200:
                data = response.json()
                download_tokens = data.get("downloadTokens")
                if download_tokens:
                    return f"{url}?alt=media&token={download_tokens}"
                return f"{url}?alt=media"

            print(f"[Storage Error]: Failed to get URL ({response.status_code}): {response.text}")
            return None

    async def download_async(self, destination_path: str) -> bool:
        """[Async] Downloads a file from Storage and saves it locally asynchronously."""
        download_url = await self.get_url_async()
        if not download_url:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.get(download_url)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
                with open(destination_path, "wb") as f:
                    f.write(response.content)
                print(f"[Success]: File downloaded async to '{destination_path}'")
                return True

            print(f"[Storage Error]: Async download failed ({response.status_code})")
            return False

    async def delete_async(self) -> bool:
        """[Async] Deletes a file from Firebase Storage asynchronously."""
        url = self._get_api_url()
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=self._get_headers())
            if response.status_code == 204:
                print(f"[Success]: File '{self.object_path}' deleted from Storage.")
                return True

            print(f"[Storage Error]: Async delete failed ({response.status_code}): {response.text}")
            return False