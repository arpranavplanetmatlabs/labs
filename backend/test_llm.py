from llm import get_client, LLM_MODEL

client = get_client()
result = client.generate(
    model=LLM_MODEL,
    prompt="test",
    system='Return JSON with extraction_confidence: 0.95 and properties: [{"name": "Density", "value": 1140, "unit": "kg/m3", "confidence": 0.95, "context": "from TDS"}]',
    temperature=0.1,
    json_mode=True,
)
print("Result:", result)
client.close()
