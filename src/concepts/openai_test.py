import os
from dotenv import load_dotenv
from openai import OpenAI

# Load API key from .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY not found in .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)

# Ask a test question
prompt = "Describe how Sanskrit transliteration works."

response = client.chat.completions.create(
    model="gpt-5",
    messages=[
        {"role": "system", "content": "You are a helpful assistant knowledgeable in linguistics."},
        {"role": "user", "content": prompt}
    ]
)

# Print response text
print(response.choices[0].message.content.strip())
