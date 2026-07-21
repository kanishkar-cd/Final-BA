import httpx
import base64
from mcp_server.schemas.azure import AzureWorkItemResponse
import re

class AzureService:
    def __init__(self, organization: str, project: str, pat_token: str):
        self.organization = organization
        self.project = project
        self.pat_token = pat_token
        self.base_url = f"https://dev.azure.com/{organization}/{project}/_apis"

    def _get_headers(self) -> dict:
        auth_string = f":{self.pat_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        return {
            "Authorization": f"Basic {encoded_auth}",
            "Accept": "application/json"
        }

    def _strip_html(self, html: str) -> str:
        if not html: return ""
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'</p>', '\n\n', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        return text.strip()

    def fetch_work_item(self, work_item_id: str) -> AzureWorkItemResponse:
        url = f"{self.base_url}/wit/workitems/{work_item_id}?api-version=7.1"
        with httpx.Client() as client:
            response = client.get(url, headers=self._get_headers())
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch work item: {response.text}")
            
            data = response.json()
            fields = data.get("fields", {})
            
            # Parse AssignedTo
            assigned_to = fields.get("System.AssignedTo", "")
            if isinstance(assigned_to, dict):
                assigned_to = assigned_to.get("displayName", "")
                
            desc = self._strip_html(fields.get("System.Description", ""))
            ac = self._strip_html(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))
            
            # Create formatted text for the workflow parser to use
            formatted = f"Title: {fields.get('System.Title', '')}\nWork Item Type: {fields.get('System.WorkItemType', '')}\n"
            if desc:
                formatted += f"\nDescription:\n{desc}\n"
            if ac:
                formatted += f"\nAcceptance Criteria:\n{ac}\n"
                
            return AzureWorkItemResponse(
                title=fields.get("System.Title", ""),
                description=desc,
                acceptance_criteria=ac,
                type=fields.get("System.WorkItemType", ""),
                formatted_text=formatted.strip(),
                metadata={
                    "id": data.get("id"),
                    "area_path": fields.get("System.AreaPath", ""),
                    "iteration": fields.get("System.IterationPath", ""),
                    "state": fields.get("System.State", ""),
                    "assigned_to": assigned_to,
                    "created_date": fields.get("System.CreatedDate", ""),
                    "tags": fields.get("System.Tags", ""),
                }
            )
