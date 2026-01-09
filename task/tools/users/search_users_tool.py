from typing import Any

from task.tools.users.base import BaseUserServiceTool


class SearchUsersTool(BaseUserServiceTool):

    @property
    def name(self) -> str:
        #TODO: Provide tool name as `search_users`
        return "search_users"

    @property
    def description(self) -> str:
        #TODO: Provide description of this tool
        description = "Searches for users in the system based on provided criteria such as name, surname, email, and gender."
        return description

    @property
    def input_schema(self) -> dict[str, Any]:
        #TODO:
        # Provide tool params Schema:
        # - name: str
        # - surname: str
        # - email: str
        # - gender: str
        # None of them are required (see UserClient.search_users method)
        schema = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The first name of the user to search for"
                },
                "surname": {
                    "type": "string",
                    "description": "The last name of the user to search for"
                },
                "email": {
                    "type": "string",
                    "description": "The email address of the user to search for"
                }
            }
        }
        return schema

    def execute(self, arguments: dict[str, Any]) -> str:
        #TODO:
        # 1. Call user_client search_users (with `**arguments`) and return its results
        # 2. Optional: You can wrap it with `try-except` and return error as string `f"Error while searching users: {str(e)}"`
        try:
            users = self._user_client.search_users(**arguments)
            return users
        except Exception as e:
            return f"Error while searching users: {str(e)}"
