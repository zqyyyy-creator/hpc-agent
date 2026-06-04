import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("PARATERA_API_KEY"),
    base_url=os.getenv("PARATERA_BASE_URL") + "/v1",
)

response = client.chat.completions.create(
    model="DeepSeek-V4-Pro",
    messages=[
        {"role": "system", "content": "你是一个超算技术支持助手。"},
        {"role": "user", "content": "如何提交一个 Slurm 作业？"},
    ],
    max_tokens=1024,
)
print(response.choices[0].message.content)