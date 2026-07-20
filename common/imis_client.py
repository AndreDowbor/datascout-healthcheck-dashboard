import requests
import json
import datetime as dt
import time
from typing import List, Dict, Any
import logging 

class IMISClient:
    def __init__(self, imis_base_url: str, imis_user: str, imis_password: str):
        """
        Initialize iMIS client with only the base URL, username, and password.
        """
        if not imis_base_url:
            raise ValueError("imis_base_url missing (e.g. https://demo123.imiscloud.com)")
        if not imis_user:
            raise ValueError("imis_user missing (e.g. demo123)")
        if not imis_password:
            raise ValueError("imis_password is missing, check your secrets manager")

        self.base_url = imis_base_url.rstrip("/")
        self.user = imis_user
        self.password = imis_password

        self.token = None
        self.token_expiration = None
        self.max_retries = 3  # safeguard against infinite loop
        self.default_token_expiry = 3600  # fallback if response doesn't give expires_in

        self.authenticate()

    def authenticate(self):
        """
        Acquire a fresh OAuth token from the iMIS endpoint. 
        Updates self.token and self.token_expiration.
        """
        data = {
            "grant_type": "password",
            "username": self.user,
            "password": self.password
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        token_url = f"{self.base_url}/token"
        response = requests.post(token_url, data=data, headers=headers)

        if response.status_code == 200:
            token_data = response.json()
            self.token = f"Bearer {token_data.get('access_token')}"
            expires_in = token_data.get("expires_in") or self.default_token_expiry
            self.token_expiration = dt.datetime.now() + dt.timedelta(seconds=expires_in)
            print(f"ℹ️[IMISClient] Token expires at {self.token_expiration}")
            print("🟢[IMISClient] Token successfully retrieved")
        else:
            raise Exception("🔴[IMISClient] Failed to authenticate with the API")

    def make_request(
        self,
        method: str,
        url: str,
        data=None,
        headers=None,
        params=None,
        retry_count=0
    ):
        """
        Core request method used by other IMISClient functions.
        Handles token refresh/retry automatically if a 401 is encountered.
        """
        if self.token_expiration is None or dt.datetime.now() >= self.token_expiration:
            print("🔔[IMISClient] Token expired or about to expire. Re-authenticating...")
            self.authenticate()

        if headers is None:
            headers = {}
        headers["Authorization"] = self.token

        try:
            response = requests.request(
                method, url, data=data, headers=headers, params=params
            )

            # If unauthorized, retry up to self.max_retries
            if response.status_code == 401 and retry_count < self.max_retries:
                print("🔴[IMISClient] 401 Unauthorized. Re-authenticating...")
                self.authenticate()
                headers["Authorization"] = self.token
                return self.make_request(
                    method, url, data, headers, params, retry_count + 1
                )

            response.raise_for_status()
            return response

        except requests.RequestException as e:
            self.log_error(f"🔴[IMISClient] Request failed: {e}")
            return None

    def fetch_iqa(
        self,
        iqa_path: str,
        limit=None,
        page_size=200,
        params=None
    ) -> list:
        """
        Fetch data from a generic IQA endpoint, handling pagination automatically.
        Returns a list of flattened records.
        """
        if isinstance(params, int):
            import warnings
            warnings.warn(
                "🔴[IMISClient] `params` provided as integer; converting to list.",
                UserWarning
            )
            params = [params]

        items = []
        offset = 0
        has_next = True
        max_pages = 10000  # Failsafe

        # Base URL construction
        base_url = f"{self.base_url}/api/IQA"
        request_params = {
            "QueryName": iqa_path,
        }
        if params:
            request_params["parameter"] = params

        total_count = None
        page_count = 0
        cumulative_fetch_duration = 0
        total_fetch_start_time = time.time()

        while has_next and (limit is None or offset < limit):
            if page_count > max_pages:
                self.log_error("Aborting after too many pages (possible API bug).")
                break

            # Adjust page size if we are close to the global limit
            current_page_size = page_size
            if limit is not None:
                remaining = limit - offset
                if remaining < page_size:
                    current_page_size = remaining

            request_params["limit"] = current_page_size
            request_params["offset"] = offset

            fetch_start_time = time.time()
            response = self.make_request("GET", base_url, params=request_params)
            fetch_duration = time.time() - fetch_start_time
            cumulative_fetch_duration += fetch_duration

            if not response:
                self.log_info(f"🔴[IMISClient] Fetch failed at offset {offset:,}. Duration: {fetch_duration:.2f}s.")
                break

            result = self._process_response(response)
            if not result:
                self.log_info(f"🔴[IMISClient] No data at offset {offset:,}, breaking.")
                break

            batch = result["items"]
            num_items = len(batch)

            if num_items == 0:
                self.log_info(f"🔴[IMISClient] Zero items returned at offset {offset:,}, breaking to avoid infinite loop.")
                break

            items.extend(batch)
            offset += num_items
            page_count += 1
            has_next = result.get("has_next", False)

            if total_count is None:
                total_count = result.get("count", 0)

            # Dynamic logging
            if total_count:
                pct = (offset / total_count) * 100
                self.log_info(
                    f"Fetched {offset:,}/{total_count:,} ({pct:.2f}%) "
                    f"in {cumulative_fetch_duration:.2f}s this batch."
                )
            else:
                self.log_info(f"Fetched {offset:,} records in {cumulative_fetch_duration:.2f}s this batch.")
            cumulative_fetch_duration = 0

        total_fetch_duration = time.time() - total_fetch_start_time
        self.log_info(
            f"🟢[IMISClient] Completed fetching in {total_fetch_duration:.2f}s. "
            f"Total records fetched: {offset:,}"
        )

        return items

    def _construct_path_request(
        self,
        path: str,
        page_size: int,
        offset: int,
        params
    ) -> str:
        """
        Helper to build the full IQA URL with limit/offset/parameters.
        """
        path_request = f"{self.base_url}{path}&limit={page_size}&offset={offset}"
        if params:
            for param in params:
                path_request += f"&parameter={param}"
        return path_request

    def _process_response(self, response):
        """
        Convert the raw JSON from iMIS into a dict with:
          - items (list of flattened records)
          - has_next (bool)
          - count (int)
        """
        try:
            data = response.json()
            return {
                "items": self._simplify_data(data),
                "has_next": data.get("HasNext", False),
                "count": data.get("TotalCount", 0)
            }
        except (json.JSONDecodeError, KeyError) as e:
            self.log_error(f"🔴[IMISClient] Error processing response: {e}")
            return None

    def _simplify_data(self, data: dict) -> list:
        """
        Flatten each record in 'Items' -> '$values' -> 'Properties' -> '$values'
        into a dict: {"FieldName": "Value", ...}
        """
        def flatten_record(row):
            rec = {}
            value_pairs = row["Properties"]["$values"]
            for value in value_pairs:
                # If 'Value' is a dict containing '$value', use that
                if isinstance(value.get("Value"), dict):
                    rec[value["Name"]] = value["Value"].get("$value", value["Value"])
                else:
                    rec[value["Name"]] = value.get("Value")
            return rec

        items = data.get("Items", {}).get("$values", [])
        return [flatten_record(item) for item in items]

    ################################################################
    #  PROPERTY BAG METHODS USING EXPLICIT ARGS FOR IQA & TABLE
    ################################################################

    def fetch_property_bag(self, iqa_path: str, member_id: str, property_name: str = None) -> list:
        """
        Retrieves property-bag records for a specific member 
        by calling iMIS IQA via the provided `iqa_path` 
        and passing member_id as a parameter.
        
        If property_name is provided, it will be passed as an additional parameter
        to filter results for that specific property.
        """
        params = [member_id]
        if property_name:
            params.append(property_name)
        
        return self.fetch_iqa(iqa_path=iqa_path, params=params)

    def delete_member_property(
        self,
        table_name: str,
        member_id: str,
        ordinal: int
    ) -> bool:
        """
        Deletes a property record in iMIS via DELETE 
        to /api/{table_name}/~{member_id}|{ordinal}.
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/api/{table_name}/~{member_id}|{ordinal}"
        response = self.make_request("DELETE", url)

        if not response or response.status_code >= 400:
            print(f"🔴[IMISClient] Delete failed for member_id='{member_id}', ordinal={ordinal}, "
                  f"status: {response.status_code if response else 'No response'}.")
            return False
        return True

    def add_member_property(
        self,
        table_name: str,
        member_id: str,
        property_name: str,
        property_type: str,
        property_value: str
    ) -> bool:
        """
        Adds a new property record to iMIS via POST /api/{table_name}.
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/api/{table_name}"

        payload = {
            "$type": "Asi.Soa.Core.DataContracts.GenericEntityData, Asi.Contracts",
            "EntityTypeName": "DataScout_Member_Properties",
            "PrimaryParentEntityTypeName": "Party",
            "Identity": {
                "$type": "Asi.Soa.Core.DataContracts.IdentityData, Asi.Contracts",
                "EntityTypeName": "DataScout_Member_Properties",
                "IdentityElements": {
                    "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
                    "$values": [str(member_id)]
                }
            },
            "PrimaryParentIdentity": {
                "$type": "Asi.Soa.Core.DataContracts.IdentityData, Asi.Contracts",
                "EntityTypeName": "Party",
                "IdentityElements": {
                    "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
                    "$values": [str(member_id)]
                }
            },
            "Properties": {
                "$type": "Asi.Soa.Core.DataContracts.GenericPropertyDataCollection, Asi.Contracts",
                "$values": [
                    {
                        "$type": "Asi.Soa.Core.DataContracts.GenericPropertyData, Asi.Contracts",
                        "Name": "ID",
                        "Value": str(member_id)
                    },
                    {
                        "$type": "Asi.Soa.Core.DataContracts.GenericPropertyData, Asi.Contracts",
                        "Name": "PropertyName",
                        "Value": property_name
                    },
                    {
                        "$type": "Asi.Soa.Core.DataContracts.GenericPropertyData, Asi.Contracts",
                        "Name": "PropertyType",
                        "Value": property_type
                    },
                    {
                        "$type": "Asi.Soa.Core.DataContracts.GenericPropertyData, Asi.Contracts",
                        "Name": "PropertyValue",
                        "Value": str(property_value)
                    }
                ]
            }
        }

        headers = {"Content-Type": "application/json"}
        response = self.make_request("POST", url, data=json.dumps(payload), headers=headers)

        if not response or response.status_code >= 400:
            print(f"🔴[IMISClient] Add failed for '{property_name}', status: {response.status_code if response else 'No response'}.")
            return False
        return True

    def upsert_member_properties(
        self,
        iqa_path: str,
        table_name: str,
        member_id: str,
        property_bag: dict
    ) -> dict:
        """
        Upsert logic that:
          1. Fetches existing properties from iMIS (via the iqa_path).
          2. For each key/value in property_bag:
             - If property exists and value is different, delete+add.
             - If property doesn't exist, add.
             - If value is the same, skip.
          3. Returns success, data, and any error.
        """
        try:
            existing_props = self.fetch_property_bag(iqa_path, member_id)
            if not isinstance(existing_props, list):
                print("🔴[IMISClient] existing_props not a list; using empty.")
                existing_props = []

            if not existing_props:
                print(f"🔎[IMISClient] No existing properties for member '{member_id}'. Will add all from property_bag.")

            for prop_name, prop_value in property_bag.items():
                normalized = prop_name.strip().lower()
                match = None
                for p in existing_props:
                    if p.get("property_name", "").strip().lower() == normalized:
                        match = p
                        break

                if match:
                    if match.get("property_value") == prop_value:
                        print(f"⚪ Skipped update for '{prop_name}' (value unchanged).")
                        continue
                    ordinal = match.get("ordinal")
                    if ordinal is None:
                        print(f"⚠️ Missing 'ordinal' for property '{prop_name}'. Skipping delete/add.")
                        continue

                    # Step 1: Delete the existing property
                    deleted = self.delete_member_property(table_name, member_id, ordinal)
                    if deleted:
                        print(f"🔵 Deleted existing property '{prop_name}' with ordinal {ordinal}, now adding updated property.")
                        # Step 2: Add the updated property
                        added = self.add_member_property(table_name, member_id, prop_name, "text", prop_value)
                        if added:
                            print(f"🔵 Updated '{prop_name}' -> '{prop_value}'")
                        else:
                            print(f"🔴 Failed to add '{prop_name}' after delete.")
                    else:
                        print(f"🔴 Failed to delete '{prop_name}' with ordinal {ordinal}.")
                else:
                    # If no match, add new
                    added = self.add_member_property(
                        table_name,
                        member_id,
                        prop_name,
                        "text",
                        prop_value
                    )
                    if added:
                        print(f"🟢 Added new property '{prop_name}' -> '{prop_value}'")
                    else:
                        print(f"🔴 Failed to add '{prop_name}'")

            # Return the existing properties (which might not reflect new items unless re-fetch)
            return {"success": True, "data": existing_props, "error": None}

        except Exception as e:
            self.log_error(f"🚨 Exception in upsert_member_properties: {e}")
            return {"success": False, "data": None, "error": e}
        

    ################################################################

    # def get_imis_document_data(self,DOCUMENT_ID):
    #     """
    #     Calls the iMIS API with the given IQA path and returns parsed JSON.

    #     Returns:
    #         dict: Parsed JSON response from the API.
    #     """
    #     url = f"{self.base_url}/api/DocumentSummary/_execute"
    #     headers = {"Content-Type": "application/json"}
        
    #     body = {
    #         "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
    #         "OperationName": "FindDescendantDocumentsInFolder",
    #         "EntityTypeName": "DocumentSummary",
    #         "Parameters": {
    #             "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
    #             "$values": [
    #             {
    #                 "$type": "System.String",
    #                 "$value": DOCUMENT_ID
    #             },
    #             {
    #                 "$type": "System.String",
    #                 "$value": ""
    #             },
    #             {
    #                 "$type": "System.Boolean",
    #                 "$value": True
    #             }
    #             ]
    #         },
    #         "ParameterTypeName": {
    #             "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
    #             "$values": [
    #             "System.String",
    #             "System.String[]",
    #             "System.Boolean"
    #             ]
    #         },
    #         "UseJson": False
    #         }

    #     response = self.make_request("POST", url, json.dumps(body), headers)
    #     return response.json()


    # def simplify_imis_documents(self,api_response):
    #     """
    #     Extracts and simplifies document metadata from an iMIS API response.

    #     Args:
    #         api_response (dict): Full JSON response from the iMIS /Document/_execute API.

    #     Returns:
    #         list[dict]: Clean list of document summaries.
    #     """
    #     simplified_docs = []
    #     raw_docs = api_response.get("Result", {}).get("$values", [])

    #     for doc in raw_docs:
    #         simplified = {
    #             "DocumentId": doc.get("DocumentId"),
    #             "Name": doc.get("Name"),
    #             "Type": doc.get("DocumentTypeId"),
    #             "Path": doc.get("Path"),
    #             "Status": doc.get("Status"),
    #             "UpdateInfo": doc.get("UpdateInfo"),
    #         }
    #         simplified_docs.append(simplified)

    #     return simplified_docs


    # def get_iqa_data(self,iqa_path):
    #     """
    #     Calls the iMIS API with the given IQA path and returns parsed JSON.

    #     Returns:
    #         dict: Parsed JSON response from the API.
    #     """
    #     url = f"{self.base_url}/api/QueryDefinition/_execute"
        
    #     headers = {
    #         "Content-Type": "application/json"
    #     }

    #     body = {
    #         "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
    #         "EntityTypeName": "QueryParameterDefinition",
    #         "OperationName": "FindByPath",
    #         "Parameters": {
    #             "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
    #             "$values": [
    #                 {
    #                     "$type": "System.String",
    #                     "$value": iqa_path
    #                 }
    #             ]
    #         },
    #         "UseJson": False,
    #         "ParameterTypeNames": {
    #             "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
    #             "$values": [
    #                 "System.String"
    #             ]
    #         }
    #     }

    #     response = self.make_request("POST", url, data=json.dumps(body), headers=headers)
    #     return response.json()
    
    
    # def fetch_and_process_imis_documents(self, DOCUMENT_PATH):
    #     """
    #     Main function to fetch and process iMIS documents using a document path.
    #     Encapsulates get_document_id within it.
    #     """

    #     def get_document_id(path):
    #         url = f"{self.base_url}/api/Document/_execute"
    #         headers = {"Content-Type": "application/json"}
            
    #         body = {
    #             "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
    #             "OperationName": "FindByPath",
    #             "EntityTypeName": "DocumentSummary",
    #             "Parameters": {
    #                 "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
    #                 "$values": [
    #                     {
    #                         "$type": "System.String",
    #                         "$value": path
    #                     }
    #                 ]
    #             },
    #             "ParameterTypeName": {
    #                 "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
    #                 "$values": [
    #                     "System.String"
    #                 ]
    #             },
    #             "UseJson": False
    #         }

    #         response = self.make_request("POST", url, json.dumps(body), headers)
    #         return response.json()

    #     # Get the document ID from the path
    #     document_id_response = get_document_id(DOCUMENT_PATH)
    #     document_id = document_id_response["Result"].get("DocumentId")

    #     if not document_id:
    #         raise ValueError("Document ID not found for the given path.")

    #     # Proceed to fetch documents under that folder
    #     document_data = self.get_imis_document_data(document_id)
        
    #     print(document_data)

    #     # Simplify and return the document summaries
    #     return self.simplify_imis_documents(document_data)

    def list_iqas_in_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        Return a list of all descendant document summaries under the specified iMIS folder path.
        Uses FindDescendantDocumentsInFolder (recursive) — returns ALL document types.
        Filter by Type == 'IQD' in the caller if you only want IQA queries.
        If the folder does not exist, return an empty list and log a warning.
        """
        document_id = self._get_document_id_from_path(folder_path)
        if not document_id:
            logging.warning(f"[IMIS] No such folder path in iMIS: '{folder_path}'")
            return []

        document_data = self._get_folder_document_summaries(document_id)
        return self._simplify_document_summaries(document_data)

    # Alias used in some notebooks
    list_documents_in_folder = list_iqas_in_folder

    def get_iqa_data(self, iqa_path: str) -> Dict[str, Any]:
        """
        Fetch the full IQA definition (fields, sources, filters) for a given IQA path.
        Returns the raw API response as a dict, including Result.Properties, Result.Sources, etc.
        """
        url = f"{self.base_url}/api/QueryDefinition/_execute"
        headers = {"Content-Type": "application/json"}
        body = {
            "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
            "EntityTypeName": "QueryParameterDefinition",
            "OperationName": "FindByPath",
            "Parameters": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
                "$values": [
                    {"$type": "System.String", "$value": iqa_path}
                ]
            },
            "UseJson": False,
            "ParameterTypeNames": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
                "$values": ["System.String"]
            }
        }
        response = self.make_request("POST", url, data=json.dumps(body), headers=headers)
        if not response:
            return {}
        return response.json()

    def _get_document_id_from_path(self, folder_path: str) -> str | None:
        """
        Look up a folder/document ID by its path.
        Returns None if not found or if API response is invalid.
        """
        url = f"{self.base_url}/api/Document/_execute"
        headers = {"Content-Type": "application/json"}
        body = {
            "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
            "OperationName": "FindByPath",
            "EntityTypeName": "DocumentSummary",
            "Parameters": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
                "$values": [
                    {"$type": "System.String", "$value": folder_path}
                ]
            },
            "ParameterTypeName": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
                "$values": ["System.String"]
            },
            "UseJson": False
        }
        response = self.make_request("POST", url, json.dumps(body), headers)
        doc_data = response.json()
        # Most environments wrap the DocumentData in a "Result" key, but some
        # iMIS versions (e.g. psansw) return the DocumentData object directly.
        result = doc_data.get("Result")
        if isinstance(result, dict):
            return result.get("DocumentId")
        if "DocumentId" in doc_data:
            return doc_data.get("DocumentId")
        return None
    
    def _get_folder_document_summaries(self, document_id: str) -> Dict[str, Any]:
        """
        Retrieve all descendant document summaries (IQAs) in the folder with the given document ID.
        """
        url = f"{self.base_url}/api/DocumentSummary/_execute"
        headers = {"Content-Type": "application/json"}
        body = {
            "$type": "Asi.Soa.Core.DataContracts.GenericExecuteRequest, Asi.Contracts",
            "OperationName": "FindDescendantDocumentsInFolder",
            "EntityTypeName": "DocumentSummary",
            "Parameters": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.Object, mscorlib]], mscorlib",
                "$values": [
                    {
                        "$type": "System.String",
                        "$value": document_id
                    },
                    {
                        "$type": "System.String",
                        "$value": ""
                    },
                    {
                        "$type": "System.Boolean",
                        "$value": True
                    }
                ]
            },
            "ParameterTypeName": {
                "$type": "System.Collections.ObjectModel.Collection`1[[System.String, mscorlib]], mscorlib",
                "$values": [
                    "System.String",
                    "System.String[]",
                    "System.Boolean"
                ]
            },
            "UseJson": False
        }
        response = self.make_request("POST", url, json.dumps(body), headers)
        return response.json()

    def _simplify_document_summaries(self, api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract document summary fields from iMIS API response and return as a list of dicts.
        """
        docs = api_response.get("Result", {}).get("$values", [])
        return [
            {
                "DocumentId": doc.get("DocumentId"),
                "Name": doc.get("Name"),
                "Type": doc.get("DocumentTypeId"),
                "Path": doc.get("Path"),
                "Status": doc.get("Status"),
                "Description": doc.get("Description"),
                "UpdateInfo": doc.get("UpdateInfo"),
            }
            for doc in docs
        ]

    ################################################################
    # Logging Helpers
    ################################################################

    def log_error(self, message: str):
        print(f"⛑️ Error: {message}")

    def log_info(self, message: str):
        print(f"ℹ️ Info: {message}")