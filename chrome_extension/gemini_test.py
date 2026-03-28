from google.genai import Client

# Hardcoded API key
api_key = "AIzaSyBrwktlI7hMvc6PhiTrRtL8lOZHA-1jxz8"

client = Client(api_key=api_key)

# Simple text generation
response = client.generate_text(
    model="text-bison-001",
    prompt="Hello! Explain recursion simply.",
    temperature=0.7,
    max_output_tokens=200
)

print(response.text)