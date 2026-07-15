import os
from dotenv import load_dotenv

# [developer-docs.sdk.python.sdk-import]
from onepassword import *
from onepassword.client import Client
from onepassword import ItemField, ItemFieldType, Website


async def init_client():
    """Initialize the 1Password client with the service account token."""

    # Load environment variables from .env file
    load_dotenv()

    # Gets your service account token from the OP_SERVICE_ACCOUNT_TOKEN environment variable.
    token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")

    # Connects to 1Password.
    client = await Client.authenticate(
        auth=token,
        # Set the following to your own integration name and version.
        integration_name="My 1Password Integration",
        integration_version="v1.0.0",
    )

    return client


async def fetch_vault():
    """Fetch the first vault from the 1Password account. 
    Will always be 'Datascout Clients' vault"""

    client = await init_client()
    vaults = await client.vaults.list()

    ds_vault_id = os.getenv("OP_VAULT_ID")
    
    # Return the first vault
    if vaults:
        for vault in vaults:
            if vault.id == ds_vault_id:
                return client, vault
    else:
        raise Exception("No vaults found")
    
    return client, None


async def fetch_client_overview(client_key):
    """Fetch all client overview based on the client key."""

    client, vault = await fetch_vault()

    if vault is None:
        print("🔴 No vault found. Please check your OP_VAULT_ID environment variable.")
        return client, None, None

    overviews = await client.items.list(vault.id)
    for overview in overviews:
        if overview.title == client_key:
            return client, vault, overview

    return client, vault, None


async def fetch_client_record(client_key):
    """Fetch the client record based on the client key."""

    client, vault, overview = await fetch_client_overview(client_key)

    # Fetch the full item using the overview's ID
    if overview is None or vault is None:
        print(f"🔴 No overview found for client key: {client_key}")
        return client, None, None
    
    item = await client.items.get(vault.id, overview.id)

    return client, vault, item


async def get_client_secrets(client_key):
    """Fetch client secrets from the item based on the client key."""

    client, vault, item = await fetch_client_record(client_key)

    if item is None or vault is None:
        print(f"🔴 No item found for client key: {client_key}")
        return client, None, None

    # Extract username, password and imis_base_url fields
    credentials = {}

    # Use generator expression to find imis_base_url
    base_imis_url = next(
        (website.url for website in item.websites if website.label == "imis_base_url"),
        None
    )
    if base_imis_url:
        credentials["imis_base_url"] = base_imis_url

    # Keep the original loop for fields
    for field in item.fields:
        if field.id in ["username", "password"]:
            credentials[field.id] = field.value
        
        # Extract client secret by title
        if field.title == "Client Secret (32-bit, use symbols & numbers)":
            credentials["sso_client_secret"] = field.value

    return credentials
    

async def create_empty_record(client, vault_id, client_key):
    """Create an empty record for the client key in the specified vault."""

    # Create an Item and add it to your vault.
    to_create = ItemCreateParams(
        title=client_key,
        category=ItemCategory.LOGIN,
        vault_id=vault_id,
    )
    created_item = await client.items.create(to_create)

    if created_item is None:
        print(f"🔴 Error creating item for client key: {client_key}")
        return None
    print(f"🟢 Successfully created empty record for client key: {client_key}")


async def upsert_to_record(client_key, data, client, record):
    """Upsert data into the client record."""

    for field in data:
        if record.fields and any(f.id == field["field_name"] for f in record.fields):
            # Update existing field
            for existing_field in record.fields:
                if existing_field.id == field["field_name"]:
                    existing_field.value = field["field_value"]
                    existing_field.field_type = field["field_type"]
                    break
        else:
            if "section" in field:
                # Create a new section if it doesn't exist
                if (record.sections and not any(f.id == field["section"] for f in record.sections)) or not record.sections:
                    # Create a new section
                    print(f"Creating new section: {field['section']}")
                    record.sections.append(
                        ItemSection(
                            id=field["section"],
                            title=field["section"],
                        )
                    )
            
            if field["field_type"] == Website:
                # Add URL field
                record.websites.append(
                    Website(
                        label=field["field_name"],
                        url=field["field_value"],
                        autofill_behavior=AutofillBehavior.ANYWHEREONWEBSITE,
                    )
                )
            else:
                # Add new field
                record.fields.append(
                    ItemField(
                        id=field["field_name"],
                        title=field["field_name"],
                        value=field["field_value"],
                        field_type=field["field_type"],
                        section_id=field.get("section", None),  # Use section_id if provided
                    )
    )
        
    updated_record = await client.items.put(record)

    if updated_record is None:
        print(f"🔴 Error updating item for client key: {client_key}")
        return None
    print(f"🟢 Successfully updated record for client key: {client_key}")


async def upsert_record(client_key, data=None):
    """Update the client record with the provided data.
    If the record does not exist, it will create an empty record."""

    # get reocrd
    client, vault, record = await fetch_client_record(client_key)

    if record is None:
        client, vault = await fetch_vault()
        await create_empty_record(client, vault.id, client_key)
        
    client, vault, record = await fetch_client_record(client_key)

    if record and data:
        print(f"🟢 Record found for client key: {client_key}")
        await upsert_to_record(client_key, data, client, record)

def flatten_onepassword_item(item):
    """
    Flattens a 1Password Item object into a dictionary.
    Returns a dict of all fields and websites by both id and title.
    Removes 'website_' and 'item_' prefixes from keys in the output.
    """
    flat = {}

    # Add basic item info
    flat['item_id'] = getattr(item, "id", None)
    flat['item_title'] = getattr(item, "title", None)
    flat['vault_id'] = getattr(item, "vault_id", None)

    # Add all fields (by both ID and Title for easy lookup)
    for field in getattr(item, "fields", []):
        # Use ID
        if hasattr(field, 'id') and field.id:
            flat[field.id] = field.value
        # Also use Title (normalized)
        if hasattr(field, 'title') and field.title:
            norm_title = field.title.strip().lower().replace(" ", "_")
            flat[norm_title] = field.value

    # Add websites (by label)
    for site in getattr(item, "websites", []):
        if hasattr(site, 'label') and site.label:
            norm_label = site.label.strip().lower().replace(" ", "_")
            flat[f'website_{norm_label}'] = site.url

    # Add sections (by title)
    if hasattr(item, "sections"):
        for section in item.sections:
            norm_title = section.title.strip().lower().replace(" ", "_")
            flat[f'section_{norm_title}'] = section.id

    # Add tags if present
    if hasattr(item, "tags") and item.tags:
        flat['tags'] = item.tags

    # Add notes if present
    if hasattr(item, "notes") and item.notes:
        flat['notes'] = item.notes

    # Post-process to strip 'website_' and 'item_' prefixes
    clean_flat = {}
    for k, v in flat.items():
        if k.startswith('website_'):
            clean_flat[k[len('website_'):]] = v
        elif k.startswith('item_'):
            clean_flat[k[len('item_'):]] = v
        else:
            clean_flat[k] = v

    return clean_flat