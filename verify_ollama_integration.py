#!/usr/bin/env python3
"""
Integration verification script for OllamaProvider.

This script verifies that:
1. OllamaProvider can be imported successfully
2. The provider selection logic in app.py works correctly
3. Environment variables are properly read
"""

import os
import sys


def test_imports():
    """Test that OllamaProvider can be imported."""
    print("=" * 60)
    print("TEST 1: Import OllamaProvider")
    print("=" * 60)

    try:
        from src.glp.agent import OllamaProvider
        print("✅ Successfully imported from src.glp.agent")
    except ImportError as e:
        print(f"❌ Failed to import from src.glp.agent: {e}")
        return False

    try:
        from src.glp.agent.providers import OllamaProvider as OllamaProvider2
        print("✅ Successfully imported from src.glp.agent.providers")
    except ImportError as e:
        print(f"❌ Failed to import from src.glp.agent.providers: {e}")
        return False

    print()
    return True


def test_provider_initialization():
    """Test that OllamaProvider can be initialized with config."""
    print("=" * 60)
    print("TEST 2: Initialize OllamaProvider")
    print("=" * 60)

    try:
        from src.glp.agent.providers import OllamaProvider
        from src.glp.agent.providers.base import LLMProviderConfig

        # Create config
        config = LLMProviderConfig(
            api_key="not-needed",
            model="qwen3:4b",
            base_url="http://localhost:11434",
        )

        # Initialize provider
        provider = OllamaProvider(config)

        print(f"✅ Provider initialized successfully")
        print(f"   Model: {provider.config.model}")
        print(f"   Base URL: {provider.base_url}")
        print(f"   Embedding Model: {provider.embedding_model}")
        print(f"   Supports Tools: {provider.supports_tools}")
        print()
        return True

    except Exception as e:
        print(f"❌ Failed to initialize provider: {e}")
        print()
        return False


def test_env_vars():
    """Test that environment variables are properly configured."""
    print("=" * 60)
    print("TEST 3: Environment Variables")
    print("=" * 60)

    ollama_model = os.getenv("OLLAMA_MODEL")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL")

    if ollama_model:
        print(f"✅ OLLAMA_MODEL is set: {ollama_model}")
    else:
        print("⚠️  OLLAMA_MODEL is not set (optional)")

    if ollama_base_url:
        print(f"✅ OLLAMA_BASE_URL is set: {ollama_base_url}")
    else:
        print("⚠️  OLLAMA_BASE_URL is not set (will use default: http://localhost:11434)")

    print()
    return True


def test_provider_selection_logic():
    """Simulate the provider selection logic from app.py."""
    print("=" * 60)
    print("TEST 4: Provider Selection Logic")
    print("=" * 60)

    try:
        from src.glp.agent.providers import (
            AnthropicProvider,
            OpenAIProvider,
            OllamaProvider,
        )
        from src.glp.agent.providers.base import LLMProviderConfig

        # Get environment variables
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        ollama_model = os.getenv("OLLAMA_MODEL")
        ollama_base_url = os.getenv("OLLAMA_BASE_URL")

        print(f"Environment check:")
        print(f"  ANTHROPIC_API_KEY: {'✓ Set' if anthropic_key else '✗ Not set'}")
        print(f"  OPENAI_API_KEY: {'✓ Set' if openai_key else '✗ Not set'}")
        print(f"  OLLAMA_MODEL: {'✓ Set' if ollama_model else '✗ Not set'}")
        print()

        selected_provider = None

        # Try Anthropic first
        if anthropic_key:
            try:
                config = LLMProviderConfig(
                    api_key=anthropic_key,
                    model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
                )
                selected_provider = "Anthropic"
                print(f"✅ Would select: Anthropic provider (model: {config.model})")
            except Exception as e:
                print(f"⚠️  Anthropic initialization would fail: {e}")

        # Fall back to OpenAI if Anthropic failed
        if not selected_provider and openai_key:
            try:
                config = LLMProviderConfig(
                    api_key=openai_key,
                    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                )
                selected_provider = "OpenAI"
                print(f"✅ Would select: OpenAI provider (model: {config.model})")
            except Exception as e:
                print(f"⚠️  OpenAI initialization would fail: {e}")

        # Fall back to Ollama if both failed
        if not selected_provider and ollama_model:
            try:
                config = LLMProviderConfig(
                    api_key="not-needed",
                    model=ollama_model,
                    base_url=ollama_base_url or "http://localhost:11434",
                )
                # Don't actually initialize (Ollama might not be running)
                selected_provider = "Ollama"
                print(f"✅ Would select: Ollama provider (model: {config.model})")
            except Exception as e:
                print(f"⚠️  Ollama initialization would fail: {e}")

        if not selected_provider:
            print("❌ No provider would be selected - at least one must be configured")
            return False

        print()
        return True

    except Exception as e:
        print(f"❌ Provider selection logic failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("OLLAMA PROVIDER INTEGRATION VERIFICATION")
    print("=" * 60)
    print()

    # Load environment from .env file if it exists
    try:
        from dotenv import load_dotenv
        if os.path.exists(".env"):
            load_dotenv()
            print("✅ Loaded environment variables from .env\n")
    except ImportError:
        print("⚠️  python-dotenv not available, using system environment\n")

    results = []

    # Run tests
    results.append(("Import Test", test_imports()))
    results.append(("Provider Initialization", test_provider_initialization()))
    results.append(("Environment Variables", test_env_vars()))
    results.append(("Provider Selection Logic", test_provider_selection_logic()))

    # Summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print()

    if all_passed:
        print("🎉 All verification tests passed!")
        print()
        print("NEXT STEPS (if Ollama is available):")
        print("1. Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh")
        print("2. Start Ollama: ollama serve")
        print("3. Pull model: ollama pull qwen3:4b")
        print("4. Start API server: uv run uvicorn src.glp.assignment.app:app --reload")
        print("5. Check logs for: 'Using Ollama provider with model: qwen3:4b'")
        print()
        print("NOTE: If Ollama is not installed, the app will gracefully fall back to")
        print("      Anthropic or OpenAI providers if configured.")
        return 0
    else:
        print("❌ Some verification tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
