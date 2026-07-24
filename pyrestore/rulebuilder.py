import os
from typing import Dict, List, Optional


class RuleBuilder:
    """
    A simple Python utility to generate production-ready
    firestore.rules and storage.rules files with custom helper functions.
    """

    def __init__(self, service_type: str = "firestore"):
        self.service_type = service_type.lower()
        if self.service_type not in {"firestore", "storage"}:
            raise ValueError("service_type must be either 'firestore' or 'storage'")

        self.functions: Dict[str, Dict[str, str]] = {}
        self.rules: List[Dict[str, str]] = []

    def add_function(self, name: str, params: List[str], expression: str) -> "RuleBuilder":
        """
        Adds a custom reusable security rule helper function.

        Example:
            builder.add_function(
                name="isOwner",
                params=["userId"],
                expression="request.auth != null && request.auth.uid == userId"
            )
        """
        self.functions[name] = {
            "params": ", ".join(params),
            "expression": expression.strip()
        }
        return self

    def allow_owner_only(self, path: str, owner_param: str = "userId") -> "RuleBuilder":
        """Shortcut: Registers and uses an isOwner helper function."""
        if "isOwner" not in self.functions:
            self.add_function(
                "isOwner",
                [owner_param],
                f"request.auth != null && request.auth.uid == {owner_param}"
            )
        return self.add_rule(path, read=f"isOwner({owner_param})", write=f"isOwner({owner_param})")

    def allow_authenticated(self, path: str, read: bool = True, write: bool = True) -> "RuleBuilder":
        """Shortcut: Registers and uses an isSignedIn helper function."""
        if "isSignedIn" not in self.functions:
            self.add_function("isSignedIn", [], "request.auth != null")

        read_cond = "isSignedIn()" if read else "false"
        write_cond = "isSignedIn()" if write else "false"
        return self.add_rule(path, read=read_cond, write=write_cond)

    def allow_public(self, path: str, read: bool = True, write: bool = False) -> "RuleBuilder":
        """Shortcut: Public read, authenticated write using isSignedIn()."""
        if "isSignedIn" not in self.functions:
            self.add_function("isSignedIn", [], "request.auth != null")

        read_cond = "true" if read else "false"
        write_cond = "isSignedIn()" if write else "false"
        return self.add_rule(path, read=read_cond, write=write_cond)

    def add_rule(
            self,
            path: str,
            read: str = "request.auth != null",
            write: str = "request.auth != null"
    ) -> "RuleBuilder":
        """Adds a custom path matcher rule."""
        cleaned_path = path.strip("/")
        self.rules.append({
            "path": cleaned_path,
            "read": read,
            "write": write
        })
        return self

    def generate(self) -> str:
        """Generates the full string contents of the security rules file."""
        lines = [
            "rules_version = '2';",
            f"service {self.service_type} {{"
        ]

        # Base service match path
        if self.service_type == "firestore":
            lines.append("  match /databases/{database}/documents {")
        else:
            lines.append("  match /b/{bucket}/o {")

        # 1. Output Helper Functions at the top of the match block
        if self.functions:
            for func_name, data in self.functions.items():
                lines.append(f"    function {func_name}({data['params']}) {{")
                lines.append(f"      return {data['expression']};")
                lines.append("    }\n")

        # 2. Output Path Rules
        for rule in self.rules:
            lines.append(f"    match /{rule['path']} {{")
            lines.append(f"      allow read: if {rule['read']};")
            lines.append(f"      allow write: if {rule['write']};")
            lines.append("    }")

        lines.append("  }")
        lines.append("}")

        return "\n".join(lines)

    def export(self, file_path: Optional[str] = None) -> str:
        """Writes the rules directly to a file."""
        default_filename = f"{self.service_type}.rules"
        out_path = file_path or default_filename

        content = self.generate()

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        abs_path = os.path.abspath(out_path)
        print(f"[Success]: Generated security rules exported to '{abs_path}'")
        return abs_path