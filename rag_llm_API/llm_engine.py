import requests

class LLMEngine:
    def __init__(self, provider="qwen", qwen_url=None, mistral_url=None):
        """
        provider: 'qwen' or 'mistral'
        qwen_url: Public Ngrok URL for Kaggle Ollama (port 11434)
        mistral_url: Public Ngrok URL for Kaggle Flask Mistral (port 5001)
        """
        self.provider = provider.lower()
        self.qwen_url = qwen_url
        self.mistral_url = mistral_url

    def generate(self, prompt, max_length=300):
        if self.provider == "qwen":
            # Send POST to Qwen Ollama Endpoint
            payload = {
                "model": "qwen3:4b", # or your pulled qwen model
                "prompt": prompt,
                "stream": False
            }
            response = requests.post(self.qwen_url, json=payload, timeout=60)
            return response.json().get("response", "")

        elif self.provider == "mistral":
            # Send POST to Mistral Flask Endpoint
            payload = {
                "prompt": prompt,
                "max_length": max_length
            }
            response = requests.post(self.mistral_url, json=payload, timeout=60)
            return response.json().get("response", "")