# Changelog

All notable changes to the `pyrestore` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-07-23

### Changed
- **Updated README**: Added descriptive text for how to use `Storage` the synchronous and asynchronous methods.

### Added
- **Storage Module**: Created a low-level storage module for accessing Firebase storage, with high-level functions
added to `FirebaseManager()`.
- **RuleBuilder**: Create an easy to use rule-builder tool for those who are new to or struggle with writing firebase rules
- **RuleBuilderCheatsheet.md**: Created a separate `.md` file for how to use the new `RuleBuilder()` tool.
---

## [1.0.2] - 2026-07-23

### Changed
- **Error Handling Refactor**: Updated `FirebaseManager.login()` , `signup()` , `get_document()` , `set_document()` , `update_document()` , `delete_document()` and `push_document()` to return descriptive dictionaries (e.g., `{"status": "success", "user_id": ...}`) allowing UI frameworks (such as Flet) to display detailed error dialogs without coupling backend logic.
---

## [1.0.0] - 2026-07-22

### Added
- **High-Level `FirebaseManager` Client**: Single unified manager for Firebase Authentication and Firestore database management.
- **Low-Level `pyrestore` Wrapper**: Pyrebase-style fluent interface (`.child().child()`) for raw Firestore REST API operations.
- **Atomic Batch Writes**: Added `batch_update()` and `batch_multi_update()` supporting uniform and mixed actions (`set`, `update`, `delete`) across multiple collections in a single request.
- **Automatic Retry Engine**: Integrated `_commit_with_retry()` with exponential backoff for network resilience on batch transactions.
- **Field Transforms**: Server-side atomic operations via `FieldValue.increment()` and `FieldValue.server_timestamp()`.
- **Automatic Type Mapping**: Full serialization and deserialization for native Python types (`datetime`, `bytes`, `bool`, `int`, `list`, `dict`).