import os
import ast
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

# Allowed modules that may import razorpay_client
ALLOWED_MODULES = {
    # The authoritative payment choke point
    os.path.normpath(os.path.join(BACKEND_DIR, "engine", "payment_engine.py")),
    # Webhook signature verification only (read-only ingress, no order/charge creation)
    os.path.normpath(os.path.join(BACKEND_DIR, "api", "routes_webhook.py")),
    # The client definition itself
    os.path.normpath(os.path.join(BACKEND_DIR, "integrations", "razorpay_client.py")),
}


def test_payment_choke_point_ast_enforcement():
    """
    AST Scanning Invariant Enforcement Test:
    Walks all Python files in backend/ and asserts that NO file outside the
    designated payment_engine.py imports razorpay_client for order/link creation.
    Fails the build if any new feature attempts to bypass the PaymentEngine choke point.
    """
    violations = []

    for root, _, files in os.walk(BACKEND_DIR):
        for f in files:
            if not f.endswith(".py"):
                continue
            file_path = os.path.normpath(os.path.join(root, f))
            if file_path in ALLOWED_MODULES:
                continue

            with open(file_path, "r", encoding="utf-8") as src_file:
                try:
                    tree = ast.parse(src_file.read(), filename=file_path)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if "razorpay_client" in alias.name or "razorpay" in alias.name:
                                violations.append(f"{file_path}:{node.lineno} imports '{alias.name}'")
                    elif isinstance(node, ast.ImportFrom):
                        module_name = node.module or ""
                        if "razorpay_client" in module_name or "razorpay" in module_name:
                            violations.append(f"{file_path}:{node.lineno} imports from '{module_name}'")

    assert not violations, (
        f"VIOLATION OF PAYMENT CHOKE POINT INVARIANT:\n"
        f"The following unauthorized modules are importing razorpay_client directly:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\nAll payment actions MUST route exclusively through 'backend.engine.payment_engine.execute_payment_mandate'."
    )
