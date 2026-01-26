"""
Vietnamese Law Chatbot using qwen7b-law-vietnamese LoRA adapter
"""
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from peft import PeftModel
import torch


def load_model():
    """Load base model with LoRA adapter"""
    base_model_id = "Qwen/Qwen2.5-7B-Instruct"
    adapter_id = "manhdungcr7/qwen7b-law-vietnamese"

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)

    print("Loading base model...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base_model, adapter_id)

    print("Model loaded successfully!")
    return model, tokenizer


def chat(model, tokenizer, question: str) -> str:
    """Generate response for a question"""
    messages = [{"role": "user", "content": question}]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Extract only the assistant response
    if "<|im_start|>assistant" in response:
        response = response.split("<|im_start|>assistant")[-1].strip()

    return response


def main():
    model, tokenizer = load_model()

    print("\n=== Vietnamese Law Chatbot ===")
    print("Type 'quit' to exit\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        if not question:
            continue

        print("Bot: ", end="", flush=True)
        response = chat(model, tokenizer, question)
        print(response)
        print()


if __name__ == "__main__":
    main()
