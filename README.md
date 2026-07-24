# pyrestore

[![PyPI Version](https://img.shields.io/pypi/v/pyrestore.svg)](https://pypi.org/project/pyrestore/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyrestore.svg)](https://pypi.org/project/pyrestore/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A simple, modern, and lightweight Python wrapper for Firebase Auth, Google Cloud Firestore, and Firebase Cloud Storage.

Powered by httpx and Pyrebase4, pyrestore provides a familiar Pyrebase-style fluent path interface (.child().child()) alongside a high-level FirebaseManager client designed for rapid, zero-boilerplate application development.

---

## Features

- High-Level Manager (FirebaseManager): A unified client wrapping Auth, Firestore, and Storage with structured response dictionaries.
- Fluent Path Chaining (pyrestore / Storage): Pyrebase-like path building for low-level database and file manipulation.
- Async & Sync Support: Built-in synchronous methods alongside asynchronous (httpx.AsyncClient) methods for non-blocking UI frameworks (like Flet or FastAPI).
- Automatic Serialization: Seamlessly handles native Python data types (datetime, int, bool, bytes, list, dict).
- Resilient Batch Operations: Multi-collection atomic writes with built-in retry logic and exponential backoff.
- Atomic Field Transforms: Server-side increments and server timestamps with FieldValue.

---

## Installation
```
pip install pyrestore
```
Note: pyrestore requires Python 3.8+ and will not work with Python 2.

---

## Getting Started

Initialize FirebaseManager for unified access, or use core pyrestore for direct database/storage access.

### High-Level Setup (FirebaseManager):
```
from pyrestore import FirebaseManager

config = {
    "apiKey": "YOUR_API_KEY",
    "authDomain": "YOUR_PROJECT.firebaseapp.com",
    "projectId": "YOUR_PROJECT_ID",
    "storageBucket": "YOUR_PROJECT.appspot.com"
}

fb = FirebaseManager(config)
```
### Low-Level Setup (pyrestore / Storage):
```
from pyrestore import pyrestore, Storage

db = pyrestore("YOUR_PROJECT_ID")
storage = Storage(project_id="YOUR_PROJECT_ID", storage_bucket="YOUR_PROJECT.appspot.com")
```

---

## Authentication

### Log In & Sign Up

FirebaseManager automatically updates and synchronizes user tokens with Firestore and Storage under the hood upon login or signup.

```
# --- LOGIN ---

# Returns a dictionary with a status key, message key, etc
fb.login("user@example.com", "Password123!")

# --- SIGN UP ---

# Validates extra required fields locally before executing network calls
signup_result = fb.signup(
    email="jane.doe@example.com",
    password="Password123!",
    required_fields=["fname", "lname"],
    fname="Jane",
    lname="Doe"
)

if signup_result["status"] == "success":
    print("Account created:", signup_result["user_id"])
```
## Asynchronous Authentication (Flet / Asyncio)

### Execute login or signup inside an asyncio loop without blocking your UI thread:
```
import asyncio

loop = asyncio.get_running_loop()

# Execute login off-thread:
result = await loop.run_in_executor(
    None, 
    fb.login, 
    "user@example.com", 
    "Password123!"
)

if result.get("status") == "success":
    print("User authenticated successfully!")
```
## Token Expiry & Refreshing
FirebaseManager automatically manages token sessions, but you can also manually trigger refreshes:

### High-level token sync:
```
fb.refresh_session(refresh_token)
```
### Low-level manual token sync:
```
db.auth(user_id_token)
storage.auth(user_id_token)
```
---

## Database (Firestore)

Build paths to your documents using standard .child() chaining.
```
db.child("users").child("user_123")
```
---
## Save Data

### `push` (Auto-Generated ID)

### High-Level:
```
fb.push_document("products", {"name": "Wireless Mouse", "price": 29.99})
```
### Low-Level:
```
data = {"name": "Wireless Mouse", "price": 29.99}
db.child("products").push(data)
```
---
### `set` (Create or Overwrite)

### High-Level (Defaults target doc_id to current user_id if omitted):
```
fb.set_document("users", {"name": "Jane Doe", "role": "admin"})
```
### Low-Level:
```
data = {"name": "Jane Doe", "role": "admin"}
db.child("users").child("user_123").set(data)
```
---
### `update` (Modify Specific Fields)

### High-Level:
```
fb.update_document("users", {"age": 30})
```
### Low-Level:
```
db.child("users").child("user_123").update({"age": 30})
```

---
### `delete` (Remove Document)

### High-Level:
```
fb.delete_document("users", "user_123")
```
### Low-Level:
```
db.child("users").child("user_123").delete()
```
---

## Multi-Location Batch Updates

 Perform atomic writes across single or multiple collections in a single transaction.

### Single Path Batch
```
fb.batch_update("users", role="admin", age=31)
```
### Multi-Collection Uniform Batch
```
fb.batch_multi_update(
    "set",
    users={"user_123": {"name": "Alex"}},
    organizations={"org_101": {"name": "Tech Corp"}}
)
```
### Multi-Collection Mixed-Action Batch
```
fb.batch_multi_update(
    users={
        "user_123": {"_action": "set", "data": {"name": "Sam", "role": "member"}}
    },
    orders={
        "order_456": {"status": "shipped"}  # Defaults to "update"
    },
    tokens={
        "token_789": {"_action": "delete"} # Deletes document
    }
)
```
---

## Retrieve Data

### High-Level (defaults to current user_id):
```
user_data = fb.get_document("users")
```
### Low-Level:
```
user = db.child("users").child("user_123").get()
all_users = db.child("users").get()
```
---

## Complex Queries

Chain query parameters together on core pyrestore references:
```
results = (
    db.child("products")
      .where("rating", ">=", 4)
      .order_by("rating", "DESC")
      .limit(5)
      .get()
)
```

- **where:** Supports operators (==, !=, <, <=, >, >=, array-contains, in, array-contains-any).
- **order_by:** Sort fields in "ASC" or "DESC" order.
- **limit:** Restrict the number of returned records.

---

## Storage (Cloud Storage)

pyrestore provides clean file upload, download, and URL retrieval support with zero boilerplate.

### 1. High-Level Storage Usage (FirebaseManager)

If no filename is provided, upload_file automatically names the file after the logged-in user_id plus the local file extension ({user_id}.png).

### Synchronous File Operations
```
# Upload Avatar (Saves as 'avatars/{user_id}.png')
res = fb.upload_file("avatars", "my_photo.png")
if res["status"] == "success":
    # Instantly store download URL in Firestore!
    fb.update_document("users", {"avatar_url": res["url"]})

# Upload with custom filename
fb.upload_file("receipts", "local_file.pdf", filename="receipt_9921.pdf")

# Get Public File URL
url = fb.get_file_url("receipts", filename="receipt_9921.pdf")

# Download File
fb.download_file("receipts", "downloads/receipt.pdf", filename="receipt_9921.pdf")

# Delete File
fb.delete_file("receipts", filename="receipt_9921.pdf")
```

### Asynchronous File Operations (Flet / Asyncio)
Non-blocking operations that prevent UI freezing during file transfers:
```
# Async Upload
res = await fb.upload_file_async("avatars", "my_photo.png")

# Async Download
await fb.download_file_async("receipts", "downloads/receipt.pdf", filename="receipt_9921.pdf")
```
---

### 2. Low-Level Storage Usage (Storage)

Access storage directly using Pyrebase-style chainable paths.

### Synchronous Storage
```
# Upload
fb.storage.child("avatars").child("user_123.png").put("path/to/local.png")

# Get Download URL
url = fb.storage.child("avatars").child("user_123.png").get_url()

# Download
fb.storage.child("avatars").child("user_123.png").download("saved.png")

# Delete
fb.storage.child("avatars").child("user_123.png").delete()
```

### Asynchronous Storage
```
# Async Upload
await fb.storage.child("avatars").child("user_123.png").put_async("path/to/local.png")

# Async Get Download URL
url = await fb.storage.child("avatars").child("user_123.png").get_url_async()

# Async Download
await fb.storage.child("avatars").child("user_123.png").download_async("saved.png")

# Async Delete
await fb.storage.child("avatars").child("user_123.png").delete_async()
```
---

## Helper Methods & Transforms

### FieldValue (Atomic Operations)

### Execute atomic server-side updates on Firestore documents:
```
from pyrestore import FieldValue

db.child("products").child("product_123").update({
    "view_count": FieldValue.increment(1),
    "updatedAt": FieldValue.server_timestamp()
})
```
---

# RuleBuilder Tool

## Easily write and export firebase rules

### RuleBuilder Setup:
```
from pyrestore import RuleBuilder
```

### Writing Firestore Rules
```
fs_rules = RuleBuilder("firestore")

# Users can only read/write their own profile
fs_rules.allow_owner_only("users/{userId}")

# Public products catalog, but only logged-in users can add products
fs_rules.allow_public("products/{productId}", read=True, write=False)

# Export to firestore.rules
fs_rules.export()
```

### Writing Storage Rules
```
storage_rules = RuleBuilder("storage")

# User avatars can only be modified by the profile owner
storage_rules.allow_owner_only("avatars/{userId}.png")

# Export to storage.rules
storage_rules.export()
```

### Writing Helper Functions
```
# Add a custom helper function to check admin status
builder.add_function(
    name="isAdmin",
    params=[],
    expression="request.auth != null && request.auth.token.admin == true"
)
```

- See `RULEBUILDER_CHEATSHEET.md` for more examples

## License

This project is licensed under the MIT License.