"""Smoke test: verifies the API key, lists usable models, makes one tiny call."""

from google import genai
from google.genai import errors

from graphtrace.config import load_settings


def main() -> None:
    settings = load_settings()
    client = genai.Client(api_key=settings.require_api_key())

    print("Models available to your key that support generateContent:")
    for model in client.models.list():
        if "generateContent" in (model.supported_actions or []):
            print(f"  {model.name}")

    print(f"\nTesting configured model: {settings.gemini_model}")
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents="Reply with exactly one word: ready",
        )
        print(f"Response: {response.text!r}")
    except errors.APIError as exc:
        print(f"API error {exc.code}: {exc.message}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()