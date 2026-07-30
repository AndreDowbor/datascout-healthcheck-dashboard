"""
onepassword_manager.py

Utility class for cleanly managing 1Password records (fetch, flatten, ensure/create, and upsert).
All core operations for working with client records are encapsulated here.

===================== USAGE EXAMPLES ==========================
import asyncio
from onepassword_manager import OnePasswordManager

async def main():
    op = OnePasswordManager()
    
    # --- Fetch & flatten ---
    secrets = await op.get_flattened_client_item("YOUR_CLIENT_KEY")
    print(secrets.get("username"))
    print(secrets.get("imis_base_url"))
    print(secrets.keys())

    # --- Upsert fields (update or add) ---
    field_updates = [
        {
            "field_name": "api_token",
            "field_value": "supersecret",
            "field_type": "STRING",  # Use correct type for your SDK
        },
        {
            "field_name": "imis_base_url",
            "field_value": "https://new.example.com",
            "field_type": "WEBSITE",  # To add/update as a website label
        },
    ]
    await op.upsert_client_record("YOUR_CLIENT_KEY", field_updates)

asyncio.run(main())

===============================================================
NOTE:
- Requires a `.env` file with OP_SERVICE_ACCOUNT_TOKEN and OP_VAULT_ID
- Install dependencies: pip install python-dotenv
- Field types: Use correct types as required by the 1Password SDK
===============================================================
"""

import os
import logging
from dotenv import load_dotenv

from onepassword import *
from onepassword.client import Client
from onepassword import ItemField, Website, ItemSection, ItemCategory, ItemCreateParams

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("onepassword_manager")


class OnePasswordManager:
    """A utility class for managing client records in 1Password."""

    def __init__(self):
        load_dotenv()
        self.token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
        self.vault_id = os.getenv("OP_VAULT_ID")
        if not self.token or not self.vault_id:
            raise EnvironmentError("OP_SERVICE_ACCOUNT_TOKEN and OP_VAULT_ID must be set in environment.")

    async def init_client(self):
        """Authenticate and return a 1Password Client instance."""
        client = await Client.authenticate(
            auth=self.token,
            integration_name="My 1Password Integration",
            integration_version="v1.0.0",
        )
        return client

    async def get_vault(self, client):
        """Fetch the vault object for this manager."""
        vaults = await client.vaults.list()
        for vault in vaults:
            if vault.id == self.vault_id:
                return vault
        logger.error(f"Vault ID {self.vault_id} not found.")
        raise ValueError("No matching vault found.")

    # === READ OPERATIONS ===

    async def fetch_client_item(self, client_key):
        """Fetch the 1Password item for the given client_key."""
        client = await self.init_client()
        vault = await self.get_vault(client)
        overviews = await client.items.list(vault.id)
        for overview in overviews:
            if overview.title == client_key:
                item = await client.items.get(vault.id, overview.id)
                return item
        logger.info(f"No item found for client key: {client_key}")
        return None

    @staticmethod
    def flatten_item(item):
        """
        Flattens a 1Password item into a flat dictionary.
        Accessible by field id, normalized title, website label, section, tags, notes, etc.
        """
        flat = {
            'id': getattr(item, "id", None),
            'title': getattr(item, "title", None),
            'vault_id': getattr(item, "vault_id", None)
        }
        for field in getattr(item, "fields", []):
            if hasattr(field, 'id') and field.id:
                flat[field.id] = field.value
            if hasattr(field, 'title') and field.title:
                norm_title = field.title.strip().lower().replace(" ", "_")
                section_id = getattr(field, "section_id", None) or getattr(getattr(field, "section", None), "id", None)
                # Fields inside a named section (e.g. "Database Information") can share a
                # display title with a top-level login field (e.g. "username"/"password").
                # Top-level (unsectioned) fields always win; a sectioned field only fills
                # the by-title key if nothing has claimed it yet.
                if section_id:
                    flat.setdefault(norm_title, field.value)
                else:
                    flat[norm_title] = field.value
        for site in getattr(item, "websites", []):
            if hasattr(site, 'label') and site.label:
                norm_label = site.label.strip().lower().replace(" ", "_")
                flat[norm_label] = site.url
        for section in getattr(item, "sections", []):
            norm_title = section.title.strip().lower().replace(" ", "_")
            flat[f'section_{norm_title}'] = section.id
        if hasattr(item, "tags") and item.tags:
            flat['tags'] = item.tags
        if hasattr(item, "notes") and item.notes:
            flat['notes'] = item.notes
        return flat

    async def get_flattened_client_item(self, client_key):
        """Fetch and flatten a 1Password item for a given client_key."""
        item = await self.fetch_client_item(client_key)
        if not item:
            logger.warning(f"No item found for key {client_key}")
            return {}
        return self.flatten_item(item)

    # === WRITE/UPSERT OPERATIONS ===

    async def ensure_client_record_exists(self, client_key):
        """
        Ensure a record for the given client_key exists in the vault.
        If missing, creates an empty record and returns the item.
        """
        item = await self.fetch_client_item(client_key)
        if item:
            return item
        client = await self.init_client()
        vault = await self.get_vault(client)
        to_create = ItemCreateParams(
            title=client_key,
            category=ItemCategory.LOGIN,
            vault_id=self.vault_id,
        )
        created_item = await client.items.create(to_create)
        if not created_item:
            logger.error(f"Failed to create item for client key: {client_key}")
            raise RuntimeError("Item creation failed.")
        logger.info(f"Created new record for client key: {client_key}")
        return created_item

    async def upsert_client_record(self, client_key, field_updates):
        """
        Upsert (create or update) fields in the client's 1Password record.

        Args:
            client_key (str): The unique key/title for the client record.
            field_updates (list of dict): List of updates, e.g.:
                [
                    {
                        "field_name": "api_token",
                        "field_value": "supersecret",
                        "field_type": "STRING",
                        "section": "API Keys",  # optional
                    },
                    {
                        "field_name": "imis_base_url",
                        "field_value": "https://new.example.com",
                        "field_type": "WEBSITE",
                    },
                ]
        """
        client = await self.init_client()
        vault = await self.get_vault(client)
        # Ensure record exists, get latest
        item = await self.ensure_client_record_exists(client_key)
        # Defensive: reload in case of creation
        item = await self.fetch_client_item(client_key)
        # Update/add fields and websites
        field_by_id = {f.id: f for f in getattr(item, "fields", [])}
        website_by_label = {w.label: w for w in getattr(item, "websites", [])}
        section_by_id = {s.id: s for s in getattr(item, "sections", [])}

        for upd in field_updates:
            name = upd.get("field_name")
            value = upd.get("field_value")
            ftype = upd.get("field_type")
            section = upd.get("section", None)

            if ftype and ftype.upper() == "WEBSITE":
                # Website field
                if name in website_by_label:
                    website_by_label[name].url = value
                else:
                    item.websites.append(
                        Website(
                            label=name,
                            url=value,
                            autofill_behavior=AutofillBehavior.ANYWHEREONWEBSITE,
                        )
                    )
            else:
                # Regular or sectioned field
                if section:
                    # Ensure section exists
                    if not any(s.id == section for s in getattr(item, "sections", [])):
                        item.sections.append(ItemSection(id=section, title=section))
                # Update existing field if present
                if name in field_by_id:
                    field = field_by_id[name]
                    field.value = value
                    if ftype:
                        field.field_type = ftype
                else:
                    # Add new field
                    item.fields.append(
                        ItemField(
                            id=name,
                            title=name,
                            value=value,
                            field_type=ftype if ftype else "STRING",
                            section_id=section if section else None,
                        )
                    )

        updated_item = await client.items.put(item)
        if not updated_item:
            logger.error(f"Failed to update item for client key: {client_key}")
            raise RuntimeError("Item update failed.")
        logger.info(f"Successfully updated record for client key: {client_key}")