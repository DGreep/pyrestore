
# RuleBuilder Setup:
```
from pyrestore import RuleBuilder

builder = RuleBuilder("firestore")
```
---
# 1. CEL Expressions in Example Helper Functions:

### Authentication Checks:
```
builder.add_function(
    name="isSignedIn",
    params=[],
    expression="request.auth != null"
)

builder.add_function(
    name="isOwner",
    params=["userId"],
    expression="isSignedIn() && request.auth.uid == userId"
)

builder.add_function(
    name="isEmailVerified",
    params=[],
    expression="isSignedIn() && request.auth.token.email_verified == true"
)
```
---
### Role / Custom Auth Claims:
```
builder.add_function(
    name="hasRole",
    params=["roleName"],
    expression="isSignedIn() && request.auth.token.role == roleName"
)

builder.add_function(
    name="isAdmin",
    params=[],
    expression="hasRole('admin')"
)
```
---
### Resource & Document Ownership Checks:
```
builder.add_function(
    name="isDocOwner",
    params=[],
    expression="isSignedIn() && resource.data.ownerId == request.auth.uid"
)
```
---
### Incoming Request Data Validation:
```
builder.add_function(
    name="isValidUserCreate",
    params=[],
    expression="request.resource.data.keys().hasAll(['email', 'createdAt', 'role']) "
               "&& request.resource.data.role in ['member', 'guest']"
)

builder.add_function(
    name="isPriceUnchanged",
    params=[],
    expression="request.resource.data.price == resource.data.price"
)
```
---
### Timestamp / Time Comparisons:
```
builder.add_function(
    name="isCreatedInPresent",
    params=[],
    expression="request.resource.data.createdAt == request.time"
)

builder.add_function(
    name="isNotExpired",
    params=[],
    expression="request.time < resource.data.expiresAt"
)
```
---
# 2. DOCUMENT MATCHERS & CEL RULES

### Public Access (Booleans):
```
# CEL String: "true" / "false"
builder.add_rule(
    path="public_catalog/{docId}",
    read="true",
    write="false"
)
```
---
### Basic Auth & Function Calls:
```
# CEL String: Reusable functions or direct request.auth checks
builder.add_rule(
    path="users/{userId}",
    read="isOwner(userId) || isAdmin()",
    write="isOwner(userId)"
)
```
---
### Resource Data Comparisons:
```
# CEL String: Checking existing stored document fields (`resource.data`)
builder.add_rule(
    path="posts/{postId}",
    read="resource.data.isPublished == true || isDocOwner()",
    write="isDocOwner() || isAdmin()"
)
```
---
### Request Data & Field Validation:
```
# CEL String: Checking incoming payload fields (`request.resource.data`)
builder.add_rule(
    path="profiles/{userId}",
    read="isSignedIn()",
    write="isOwner(userId) && isValidUserCreate()"
)
```
---
### Immutable Field Checks on Update:
```
# CEL String: Comparing new payload against existing document data
builder.add_rule(
    path="products/{productId}",
    read="true",
    write="isAdmin() || (isSignedIn() && isPriceUnchanged())"
)
```
---
### String Operations & Type Checks:
```
# CEL String: `.size()`, `.matches()`, `.startsWith()`
builder.add_rule(
    path="comments/{commentId}",
    read="true",
    write="isSignedIn() "
          "&& request.resource.data.text is string "
          "&& request.resource.data.text.size() > 0 "
          "&& request.resource.data.text.size() <= 500"
)
```
---
### Map & List Membership Operations:
```
# CEL String: `in`, `.hasAny()`, `.hasAll()`
builder.add_rule(
    path="projects/{projectId}",
    read="request.auth.uid in resource.data.memberIds",
    write="resource.data.roles[request.auth.uid] in ['owner', 'editor']"
)
```
---
### Cross-Document Lookups (exists / get):
```
# CEL String: Firestore database queries (`exists()`, `get()`)
builder.add_rule(
    path="teams/{teamId}/documents/{docId}",
    read="exists(/databases/$(database)/documents/teams/$(teamId)/members/$(request.auth.uid))",
    write="get(/databases/$(database)/documents/teams/$(teamId)).data.ownerId == request.auth.uid"
)
```
---
# 3. EXPORT FILE
```
builder.export("firestore.rules")
```
---