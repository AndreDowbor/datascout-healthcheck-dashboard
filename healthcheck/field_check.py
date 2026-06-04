"""
field_check.py — Check if a specific field exists in a specific IQA across all environments.

Usage:
    python3 healthcheck/field_check.py
    python3 healthcheck/field_check.py --iqa contact_by_id --field language_preference
"""

import asyncio
import json
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from common.onepassword_manager import OnePasswordManager
from common.imis_client import IMISClient

IQA_ROOT = "$/_DataScout"

CLIENT_IDS = [
    "demo83",
    "aaae", "atsdemo89", "aboncle", "armdemo96", "imisdemo11", "imis36",
    "apimisdemo25", "imis87", "imis104", "demosales3", "demosales50", "demosales39", "demosales28",
    "atdemo2", "atdemo81", "demo42", "bsidemo27", "demo86",
    "ensyncdemo13", "i8vdemo13", "ibcdemo80", "isgdemo14", "isgdemo106",
    "oasw", "cpanb",
]

URL_OVERRIDES = {
    "cpanb": "https://staff.cpanewbrunswick.ca/",
    "demosales50": "https://demosales50.imiscloud.com/",
}



def check_field_in_env(client: IMISClient, iqa_path: str, field_name: str) -> dict:
    """
    Returns dict with keys: status, has_field, detail
      status: 'present' | 'absent' | 'iqa_not_found' | 'error'

    NOTE: QueryDefinition column Names are internal IDs like '{guid}.CL{n}', not
    human-readable aliases. We search the raw JSON string for the field name instead,
    where it appears inside SQL expressions e.g. [DataScout_Data].[language_preference].
    """
    try:
        definition = client.get_iqa_data(iqa_path)

        if not definition:
            return {"status": "error", "has_field": False, "detail": "Empty response"}

        if definition.get("Result") is None:
            return {"status": "iqa_not_found", "has_field": False,
                    "detail": "Result is null — IQA not found at this path"}

        raw_json = json.dumps(definition).lower()
        has_field = field_name.lower() in raw_json

        return {
            "status": "present" if has_field else "absent",
            "has_field": has_field,
            "detail": "searched raw JSON definition",
        }

    except Exception as e:
        return {"status": "error", "has_field": False, "detail": str(e)[:120]}


def discover_iqa_path(client: IMISClient, iqa_name: str) -> str | None:
    """
    Find the exact iMIS path of an IQA by searching under IQA_ROOT.
    Returns the full path (e.g. '$/_DataScout/Contacts/contact_by_id') or None.
    """
    try:
        all_docs = client.list_iqas_in_folder(IQA_ROOT)
        for doc in all_docs:
            if doc.get("Type") == "IQD":
                name = (doc.get("Name") or "").lower()
                path = doc.get("Path") or ""
                if name == iqa_name.lower() or path.lower().endswith("/" + iqa_name.lower()):
                    return path
        # Also accept partial match
        for doc in all_docs:
            if doc.get("Type") == "IQD":
                name = (doc.get("Name") or "").lower()
                if iqa_name.lower() in name:
                    return doc.get("Path")
    except Exception as e:
        print(f"  [warn] Path discovery failed: {e}")
    return None


async def main(iqa_name: str, field_name: str, iqa_full_path: str | None = None):
    op = OnePasswordManager()

    print(f"\nField check: '{field_name}' in IQA '{iqa_name}'")
    print(f"{'='*60}\n")

    # Fetch credentials
    print("Fetching credentials from 1Password...")
    environment_credentials = {}
    for client_id in CLIENT_IDS:
        try:
            secrets = await op.get_flattened_client_item(client_id)
            base_url = secrets.get("imis_base_url")
            username = secrets.get("username")
            password = secrets.get("password")
            if not all([base_url, username, password]):
                continue
            environment_credentials[client_id] = {
                "imis_base_url": base_url,
                "username": username,
                "password": password,
            }
        except Exception:
            pass

    for env, url in URL_OVERRIDES.items():
        if env in environment_credentials:
            environment_credentials[env]["imis_base_url"] = url

    print(f"Loaded {len(environment_credentials)} environments.\n")

    # ── Step 1: Discover exact IQA path from demo83 ─────────────────────────
    ref_env = "demo83"
    print(f"REFERENCE: {ref_env} — discovering IQA path...")

    ref_creds = environment_credentials.get(ref_env)
    if not ref_creds:
        print(f"  ❌ demo83 credentials not found. Aborting.")
        return

    ref_client = IMISClient(ref_creds["imis_base_url"], ref_creds["username"], ref_creds["password"])

    if iqa_full_path:
        iqa_path = iqa_full_path
        print(f"  Using provided path: {iqa_path}")
    else:
        iqa_path = discover_iqa_path(ref_client, iqa_name)
        if not iqa_path:
            iqa_path = f"{IQA_ROOT}/AiParts/Profile/{iqa_name}"
            print(f"  ⚠️  IQA not found by discovery — using default path: {iqa_path}")
        else:
            print(f"  ✅ Found IQA path: {iqa_path}")

    # ── Step 2: Check reference (demo83) ────────────────────────────────────
    print(f"\n── demo83 (reference) ──")
    ref_result = check_field_in_env(ref_client, iqa_path, field_name)

    if ref_result["status"] == "iqa_not_found":
        print(f"  ❌ IQA not found in demo83 at path '{iqa_path}'")
        print("  Cannot proceed without a valid reference. Check the IQA name.")
        return
    elif ref_result["status"] == "error":
        print(f"  ⚠️  Error: {ref_result['detail']}")
    else:
        icon = "✅" if ref_result["has_field"] else "❌"
        print(f"  '{field_name}': {icon} {'PRESENT' if ref_result['has_field'] else 'ABSENT'}")

    # ── Step 3: Check all other environments ─────────────────────────────────
    results = {"present": [], "absent": [], "error": [], "iqa_not_found": []}

    other_envs = [e for e in environment_credentials if e != ref_env]
    print(f"\n{'='*60}")
    print(f"CHECKING {len(other_envs)} OTHER ENVIRONMENTS")
    print(f"{'='*60}\n")

    for env in other_envs:
        creds = environment_credentials[env]
        try:
            client = IMISClient(creds["imis_base_url"], creds["username"], creds["password"])
        except Exception as e:
            print(f"  {env:<20} ⚠️  Login failed: {str(e)[:60]}")
            results["error"].append(env)
            continue

        r = check_field_in_env(client, iqa_path, field_name)

        if r["status"] == "present":
            print(f"  {env:<20} ✅ PRESENT")
            results["present"].append(env)
        elif r["status"] == "absent":
            print(f"  {env:<20} ❌ ABSENT")
            results["absent"].append(env)
        elif r["status"] == "iqa_not_found":
            print(f"  {env:<20} — IQA not in this env")
            results["iqa_not_found"].append(env)
        else:
            print(f"  {env:<20} ⚠️  ERROR: {r['detail']}")
            results["error"].append(env)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"SUMMARY — '{field_name}' in '{iqa_name}'")
    print(f"IQA path: {iqa_path}")
    print(f"{'='*60}")
    print(f"  ✅ Present        ({len(results['present'])}): {', '.join(results['present']) or '—'}")
    print(f"  ❌ Absent         ({len(results['absent'])}): {', '.join(results['absent']) or '—'}")
    print(f"  — IQA not in env ({len(results['iqa_not_found'])}): {', '.join(results['iqa_not_found']) or '—'}")
    print(f"  ⚠️  Error          ({len(results['error'])}): {', '.join(results['error']) or '—'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check if a field exists in an IQA across all environments")
    parser.add_argument("--iqa",   default="contact_by_id",      help="IQA name (default: contact_by_id)")
    parser.add_argument("--field", default="language_preference", help="Field name to search for (default: language_preference)")
    parser.add_argument("--path",  default=None,                  help="Full IQA path — skips discovery (e.g. '$/_DataScout/AiParts/Profile/contact_by_id')")
    args = parser.parse_args()

    asyncio.run(main(iqa_name=args.iqa, field_name=args.field, iqa_full_path=args.path))
