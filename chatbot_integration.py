# -*- coding: utf-8 -*-
"""Chatbot integration.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1O3EdzjI9J33P0sjIJ8DXP2FWOv0Gmm_f
"""

import logging
import pandas as pd

from google.colab import drive
drive.mount('/content/drive')

!pip install python-telegram-bot

from transformers import AutoModelForCausalLM, AutoTokenizer

from google.colab import userdata
import os

!pip install redis
import redis
!pip install celery
from celery import Celery

redis_conn = redis.StrictRedis(host='localhost', port=6379, db=0)

from google.colab import userdata
import os
!pip install pyTelegramBotAPI
import telebot
app = Celery('chatbot', broker=os.getenv('CELERY_BROKER_URL'))

TELEGRAM_BOT_TOKEN = userdata.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

app.conf.update(
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
)

app.config_from_object('celery_config')
app.autodiscover_tasks()

conversations = {}

SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT')

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_name = "polinasch/gpt2-small-arabic-finetuned-masry-final"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
model.to(device)

def tokenize(input_texts):
    return tokenizer(input_texts, return_tensors='pt', padding=True, truncation=True)

df = pd.read_csv('/content/drive/MyDrive/Arabic subtitles.xlsx - renewed.csv')

df = df.rename(columns={df.columns[0]: 'text'})

df = df[~df['text'].str.contains(r'\[[^\]]+\]')]

import re

def clean_text(text):
    cleaned_text = re.sub(r'[^\u0600-\u06FF\s]', '', text)
    return cleaned_text

df['cleaned_text'] = df['text'].apply(clean_text)

cleaned_df = df[df['cleaned_text'].str.strip() != '']

print(cleaned_df)

texts = cleaned_df['text'].tolist()

def generate_response_with_model_and_faiss(message_list, model, tokenizer, device):
    """
    Generate a response to a message using the model, tokenizer
    """
    print(f"Model device: {next(model.parameters()).device}")

    text_inputs = [message['content'] for message in message_list]

    inputs = tokenizer(text_inputs, return_tensors="pt", padding=True, truncation=True, max_length=512)
    print(f"Inputs: {inputs}")

    input_ids = inputs['input_ids'].to(device)
    attention_mask = inputs['attention_mask'].to(device)

    sample_outputs = model.generate(
        input_ids,
        attention_mask=attention_mask,
        do_sample=True,
        temperature=0.7,
        top_k=50,
        max_length=200,
        top_p=0.8,
        num_return_sequences=3,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )

    print(f"Sample outputs: {sample_outputs}")

    responses = []
    for sample_output in sample_outputs:
        response_text = tokenizer.decode(sample_output, skip_special_tokens=True)
        truncated_response = response_text[:4000] if len(response_text) > 4000 else response_text
        responses.append(truncated_response.strip())

    print(f"Generated responses: {responses}")

    return responses

def conversation_tracking(text_message, user_id):
    """
    Track and manage conversations for a user.
    """
    user_conversations = conversations.get(user_id, {'conversations': [], 'responses': []})

    user_messages = user_conversations['conversations'] + [text_message]
    user_responses = user_conversations['responses']

    conversation_history = []
    for i in range(len(user_messages)):
        conversation_history.append({
            "role": "user", "content": user_messages[i]
        })
        if i < len(user_responses):
            conversation_history.append({
                "role": "assistant", "content": user_responses[i]
            })

    conversation_history.append({
        "role": "user", "content": text_message
    })

    print("Message list for tokenization:", conversation_history)

    responses = generate_response_with_model_and_faiss(conversation_history, model, tokenizer, device)

    print("Generated responses:", responses)

    if responses:
        user_responses.append(responses[0])

    conversations[user_id] = {'conversations': user_messages, 'responses': user_responses}

    return responses[0] if responses else "Sorry, I didn't understand that."

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

@app.task
def send_welcome_message(chat_id):
    welcome_text = (
        "🌟 Salam! Welcome to the Egyptian Arabic Adventure Bot! 🌟\n\n"
        "Embark on an exciting journey to master the beautiful Egyptian Arabic language. 🗺️✨\n\n"
        "To start your adventure, simply click on /start and let the magic unfold! ✨📚\n\n"
        "Ready to dive into the wonders of Egyptian Arabic? Let's get started!"
    )
    try:
        bot.send_message(chat_id=chat_id, text=welcome_text)
        logging.info(f"Message sent to chat_id: {chat_id}")
    except Exception as e:
        logging.error(f"Failed to send message to chat_id: {chat_id}, error: {e}")

@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = (
                    "Yalla!\n"
                    "/start - See available commands\n"
                    "/model - Get information about the model\n"
                    "/exercise - Get an exercise prompt\n"
                    "/clear - Clear the conversation history")
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['clear'])
def clear_history(message):
    global conversations
    user_id = message.chat.id
    conversations[user_id] = {'conversations': [], 'responses': []}
    bot.reply_to(message, "Conversations and responses cleared!")

import random

def generate_random_exercise(sentences):
    """
    Generates a random exercise from the list of sentences.

    Args:
        sentences (list): List of sentences to choose from.

    Returns:
        tuple: Contains the exercise sentence with a blank, the correct word, and the list of options.
    """
    if not sentences:
        return None, None, None

    sentence = random.choice(sentences)
    words = sentence.split()

    if len(words) < 2:
        return None, None, None

    blank_index = random.randint(0, len(words) - 1)
    correct_word = words[blank_index]
    words[blank_index] = '____'

    options = [correct_word]
    all_words = ' '.join(sentences).split()
    while len(options) < 4:
        word = random.choice(all_words)
        if word not in options:
            options.append(word)

    random.shuffle(options)
    exercise = ' '.join(words)

    return exercise, correct_word, options

sentences = cleaned_df['text'].tolist()
exercise_text, correct_word, options = generate_random_exercise(sentences)

print("Exercise Sentence: ", exercise_text)
print("Correct Word: ", correct_word)
print("Options: ", options)

# Генерация упражнений, в процессе подготовки
#@bot.message_handler(commands=['exercise'])
#def handle_exercise_command(message):
#    user_id = message.chat.id

#    user_states[user_id] = 'exercise'

    #task = generate_exercise_task.delay()

#    def send_exercise():
#        while not task.ready():
#            asyncio.sleep(1)

#        exercise_text, correct_word, options = task.result

#        if exercise_text is None:
#            bot.send_message(user_id, "No exercise could be generated.")
#            return

 #       options_text = '\n'.join(f"{i+1}. {opt}" for i, opt in enumerate(options))

  #      message_text = f"Complete the sentence:\n{exercise_text}\n\nOptions:\n{options_text}"
  #      bot.send_message(user_id, message_text)

   # import threading
   # threading.Thread(target=send_exercise).start()

user_states = {}

@bot.message_handler(commands=['model'])
def handle_model_command(message):
    user_id = message.chat.id
    user_states[user_id] = 'model'
    bot.reply_to(message, "You are now chatting with the model. Type your messages to start.")

@bot.message_handler(commands=['exercise'])
def handle_exercise_command(message):
    user_id = message.chat.id
    user_states[user_id] = 'exercise'
    bot.reply_to(message, "This feature is in progress, stay tuned!")

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    bot.reply_to(message, "Send /model to start chatting with the model or /exercise to enter exercise mode.")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.chat.id
    state = user_states.get(user_id)

    if state == 'model':
        handle_model_state(message)
    elif state == 'exercise':
        handle_exercise_state(message)
    else:
        bot.reply_to(message, "Send /model to start chatting with the model or /exercise to enter exercise mode.")

def handle_model_state(message):
    user_id = message.chat.id
    response = conversation_tracking(message.text,user_id)
    bot.reply_to(message, response)

def handle_exercise_state(message):
    user_id = message.chat.id
    user_data = user_states.get(user_id)

if __name__ == "__main__":
    print("Starting bot...")
    print("Bot Started")
    print("Press Ctrl + C to stop bot")
    bot.polling()

