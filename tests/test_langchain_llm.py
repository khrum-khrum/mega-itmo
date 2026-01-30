"""Unit tests for src/utils/langchain_llm.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.langchain_llm import LangChainAgent


class TestLangChainAgentInit:
    """Tests for LangChainAgent initialization."""

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_init_with_explicit_api_key(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should initialize with explicitly provided API key."""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm
        mock_create_agent.return_value = MagicMock()

        tools = [MagicMock()]
        agent = LangChainAgent(tools=tools, api_key="test-api-key")

        assert agent.api_key == "test-api-key"
        assert agent.model == "llama-3.3-70b-versatile"
        assert agent.tools == tools
        mock_chat_openai.assert_called_once()
        mock_create_agent.assert_called_once()

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-api-key"})
    def test_init_with_env_api_key(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should use API key from environment variable."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        agent = LangChainAgent(tools=[])

        assert agent.api_key == "env-api-key"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_init_with_custom_model(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should accept custom model name."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        agent = LangChainAgent(
            tools=[], api_key="test-key", model="anthropic/claude-3.5-sonnet"
        )

        assert agent.model == "anthropic/claude-3.5-sonnet"
        mock_chat_openai.assert_called_once()
        call_kwargs = mock_chat_openai.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3.5-sonnet"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_init_with_custom_base_url(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should accept custom base URL."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        LangChainAgent(
            tools=[], api_key="test-key", base_url="https://custom-api.example.com/v1"
        )

        call_kwargs = mock_chat_openai.call_args[1]
        assert call_kwargs["openai_api_base"] == "https://custom-api.example.com/v1"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    @patch.dict("os.environ", {"LLM_BASE_URL": "https://env-api.example.com/v1"})
    def test_init_with_env_base_url(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should use base URL from environment variable."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        LangChainAgent(tools=[], api_key="test-key")

        call_kwargs = mock_chat_openai.call_args[1]
        assert call_kwargs["openai_api_base"] == "https://env-api.example.com/v1"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_api_key_raises_error(self) -> None:
        """Should raise ValueError when no API key is available."""
        with pytest.raises(ValueError, match="API key not found"):
            LangChainAgent(tools=[])

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_init_default_base_url(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should use Groq API as default base URL."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        # Clear LLM_BASE_URL to test default
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"}, clear=True):
            LangChainAgent(tools=[], api_key="test-key")

        call_kwargs = mock_chat_openai.call_args[1]
        assert call_kwargs["openai_api_base"] == "https://api.groq.com/openai/v1"


class TestLangChainAgentRun:
    """Tests for LangChainAgent.run method."""

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_run_returns_output(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should return agent output in expected format."""
        mock_chat_openai.return_value = MagicMock()

        # Create mock message with content
        mock_message = MagicMock()
        mock_message.content = "Task completed successfully"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_message]}
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")
        result = agent.run("Fix the bug in main.py")

        assert result["output"] == "Task completed successfully"
        assert "messages" in result
        mock_agent.invoke.assert_called_once()

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_run_invokes_with_correct_format(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should invoke agent with proper message format."""
        mock_chat_openai.return_value = MagicMock()

        mock_message = MagicMock()
        mock_message.content = "Done"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_message]}
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")
        agent.run("Test issue description")

        call_args = mock_agent.invoke.call_args[0][0]
        assert "messages" in call_args
        assert call_args["messages"][0]["role"] == "user"
        assert call_args["messages"][0]["content"] == "Test issue description"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_run_handles_message_without_content_attr(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should handle messages that don't have content attribute."""
        mock_chat_openai.return_value = MagicMock()

        # Message without content attribute (string representation fallback)
        mock_message = "Simple string message"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_message]}
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")
        result = agent.run("Fix bug")

        assert result["output"] == "Simple string message"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_run_raises_runtime_error_on_failure(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should raise RuntimeError when agent execution fails."""
        mock_chat_openai.return_value = MagicMock()

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = Exception("LLM API error")
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")

        with pytest.raises(RuntimeError, match="Error running agent: LLM API error"):
            agent.run("This will fail")


class TestLangChainAgentStream:
    """Tests for LangChainAgent.stream method."""

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_stream_yields_values(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should yield agent execution steps."""
        mock_chat_openai.return_value = MagicMock()

        # Simulate streaming output
        stream_outputs = [
            {"messages": ["Step 1"]},
            {"messages": ["Step 2"]},
            {"messages": ["Final step"]},
        ]

        mock_agent = MagicMock()
        mock_agent.stream.return_value = iter(stream_outputs)
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")
        results = list(agent.stream("Stream this issue"))

        assert len(results) == 3
        assert results[0]["messages"] == ["Step 1"]
        assert results[2]["messages"] == ["Final step"]

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_stream_invokes_with_correct_format(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should stream with proper message format and stream mode."""
        mock_chat_openai.return_value = MagicMock()

        mock_agent = MagicMock()
        mock_agent.stream.return_value = iter([])
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")
        list(agent.stream("Stream test"))

        call_args = mock_agent.stream.call_args
        assert call_args[0][0]["messages"][0]["role"] == "user"
        assert call_args[0][0]["messages"][0]["content"] == "Stream test"
        assert call_args[1]["stream_mode"] == "values"

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_stream_raises_runtime_error_on_failure(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """Should raise RuntimeError when streaming fails."""
        mock_chat_openai.return_value = MagicMock()

        mock_agent = MagicMock()
        mock_agent.stream.side_effect = Exception("Stream error")
        mock_create_agent.return_value = mock_agent

        agent = LangChainAgent(tools=[], api_key="test-key")

        with pytest.raises(RuntimeError, match="Error streaming agent: Stream error"):
            list(agent.stream("This will fail"))


class TestLangChainAgentSystemPrompt:
    """Tests for LangChainAgent system prompt configuration."""

    def test_system_prompt_contains_workflow(self) -> None:
        """System prompt should contain workflow instructions."""
        assert "WORKFLOW:" in LangChainAgent.SYSTEM_PROMPT
        assert "Understand the Issue" in LangChainAgent.SYSTEM_PROMPT
        assert "Explore the Repository" in LangChainAgent.SYSTEM_PROMPT

    def test_system_prompt_contains_tool_instructions(self) -> None:
        """System prompt should mention available tools."""
        prompt = LangChainAgent.SYSTEM_PROMPT
        assert "get_file_tree" in prompt
        assert "read_file" in prompt
        assert "update_file" in prompt
        assert "create_file" in prompt
        assert "search_code" in prompt
        assert "run_command" in prompt

    @patch("src.utils.langchain_llm.create_agent")
    @patch("src.utils.langchain_llm.ChatOpenAI")
    def test_system_prompt_passed_to_agent(
        self, mock_chat_openai: MagicMock, mock_create_agent: MagicMock
    ) -> None:
        """System prompt should be passed to create_agent."""
        mock_chat_openai.return_value = MagicMock()
        mock_create_agent.return_value = MagicMock()

        LangChainAgent(tools=[], api_key="test-key")

        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["system_prompt"] == LangChainAgent.SYSTEM_PROMPT
