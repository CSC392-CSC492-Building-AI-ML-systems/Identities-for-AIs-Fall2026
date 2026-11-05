# LoRA Fine-Tuning

The goal is to see whether a small open-weight model, fine-tuned with LoRA, can look at a chatbot answer and say which model wrote it. 
Our mentor said that a few hundred records is enough for fine-tuning, and that the point is to get experience with the process even if the results are weak.

## Method

- **Base model:** Qwen2.5-0.5B (small and open-weight)
- **Task:** classification. The model reads one answer and picks one of the 5 models.
- **LoRA settings:** rank 16, alpha 32, dropout 0.05, applied to the attention and feed-forward layers
- **Training:** 4 epochs, learning rate 2e-4, effective batch size 16, first ~384 tokens of each answer
- **Train/test split:** split by **question**, not by record. About 7 questions were held out completely for testing. Every question was asked many times, so a random split would put near-copies of the same answer in both train and test and inflate the score.
- **Class balance:** at most 200 training examples per model (98 for Qwen3.5-9B)
- **Sizes:** 898 training examples, 697 test examples
- **Baseline:** a simple word-counting method (TF-IDF + logistic regression) trained on the same data

## Files

- `lora_llm_identification.ipynb`: the Colab notebook (data prep, baseline, training, evaluation)
- `adapter_model.safetensors` and `adapter_config.json`: the trained LoRA adapter

## How to reproduce

1. Open the notebook in Google Colab and switch to a T4 GPU.
2. Upload the five fingerprinting `.jsonl` files.
3. Run the cells in order.

*This README will be updated as the work continues.*
