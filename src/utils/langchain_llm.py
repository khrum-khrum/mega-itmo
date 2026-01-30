"""LangChain-based LLM client with OpenRouter integration."""

import os
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

load_dotenv()


class LangChainAgent:
    """
    LangChain-based agent for code generation.

    Uses OpenRouter for LLM access and custom tools for repository operations.
    """

    SYSTEM_PROMPT = """You are an expert software engineer working with GitHub repositories.

Your task is to analyze GitHub Issues and implement solutions by modifying code in the cloned repository.

WORKFLOW:
1. **Understand the Issue**: Carefully read the issue description to understand what needs to be done
2. **Explore the Repository**: Use available tools to understand the codebase:
   - Use `get_file_tree` to see the project structure
   - Use `list_directory` to explore specific directories
   - Use `read_file` to examine existing code and configuration files
   - Use `search_code` to find relevant functions, classes, or patterns
3. **Plan the Solution**: Think about what files need to be created, modified, or deleted
4. **Implement Changes**: Use the file operation tools:
   - `create_file` for new files
   - `update_file` for modifying existing files
   - `delete_file` if files need to be removed
5. **Verify**: Use `run_command` to run tests or build commands if needed
6. **Review**: Use `get_git_diff` to see what changes were made

IMPORTANT GUIDELINES:
- Always read files before modifying them to understand the existing code structure
- Follow the existing code style and conventions in the repository
- Make sure file paths are correct relative to the repository root
- When updating files, provide the COMPLETE new content, not just diffs
- Test your changes if possible using `run_command`
- Be thorough but efficient - don't make unnecessary changes

TOOL USAGE:
- Start by exploring the repository structure with `get_file_tree` and `list_directory`
- Read relevant existing files with `read_file` to understand the codebase
- Search for specific patterns with `search_code` if needed
- Create or update files with `create_file` and `update_file`
- Verify changes with `get_git_diff` before finishing

After implementing the solution, summarize what you did and what files were changed.
"""

    def __init__(
        self,
        tools: list,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        base_url: str | None = None,
    ):
        """
        Initialize the LangChain agent.

        Args:
            tools: List of LangChain tools to provide to the agent
            api_key: OpenRouter API key (or from env var OPENROUTER_API_KEY)
            model: Model identifier (OpenRouter format)
            base_url: Base URL for LLM API (or from env var LLM_BASE_URL, defaults to OpenRouter)
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. "
                "Pass it as argument or set OPENROUTER_API_KEY environment variable."
            )

        self.model = model
        self.tools = tools

        # Get base_url from parameter, environment variable, or use default
        resolved_base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

        # Initialize OpenAI-compatible client pointing to OpenRouter
        self.llm = ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            openai_api_base=resolved_base_url,
            temperature=0.2,
            max_tokens=4096,
        )

        # Create the agent using the new LangChain 1.2+ API
        self.agent = create_agent(
            self.llm,
            tools=tools,
            system_prompt=self.SYSTEM_PROMPT,
        )

    def run(self, issue_description: str) -> dict[str, Any]:
        """
        Run the agent on a GitHub Issue.

        Args:
            issue_description: Description of the GitHub Issue to solve

        Returns:
            Agent execution result with output and intermediate steps
        """
        try:
            # New API uses messages format
            input_message = {"role": "user", "content": issue_description}
            result = self.agent.invoke({"messages": [input_message]})

            # Extract the final message content for compatibility
            final_message = result["messages"][-1]
            return {
                "output": final_message.content if hasattr(final_message, "content") else str(final_message),
                "messages": result["messages"],
            }
        except Exception as e:
            raise RuntimeError(f"Error running agent: {str(e)}") from e

    def stream(self, issue_description: str):
        """
        Stream the agent execution for real-time output.

        Args:
            issue_description: Description of the GitHub Issue to solve

        Yields:
            Agent execution steps as they happen
        """
        try:
            input_message = {"role": "user", "content": issue_description}
            for step in self.agent.stream(
                {"messages": [input_message]},
                stream_mode="values",
            ):
                yield step
        except Exception as e:
            raise RuntimeError(f"Error streaming agent: {str(e)}") from e
