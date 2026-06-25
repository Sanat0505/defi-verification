import os, json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are a DeFi transaction intent parser.
Extract the user's intent and return ONLY valid JSON.
No explanation, no markdown, no extra text.

Required format:
{
  "action":    "swap" | "supply" | "transfer" | "approve" | "withdraw" | "borrow" | "repay",
  "protocol":  string (e.g. "Uniswap V3", "Aave V3"),
  "token_in":  string (e.g. "USDC", "WETH", "DAI"),
  "token_out": string or null,
  "amount":    number or null,
  "chain":     "Ethereum"
}

Rules:
- NEVER include a contract address or wallet address
- Use standard token symbols (USDC, WETH, DAI, WBTC)
- Use full protocol names (Uniswap V3, Aave V3)
- If action is supply/deposit/borrow/repay, token_out is null
- If intent is unclear, return {"error": "Could not parse intent"}
"""

async def parse_intent(prompt: str) -> dict:
    try:
        response = client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system",  "content": SYSTEM_PROMPT},
                {"role": "user",    "content": prompt}
            ],
            temperature = 0,
            max_tokens  = 200
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json","").replace("```","").strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "LLM returned invalid JSON"}
    except Exception as e:
        return {"error": str(e)}