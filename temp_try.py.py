import logging
import base64
import requests
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient



# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram bot token
TELEGRAM_TOKEN = '8018511188:AAFHTr-KwLjJ8ke2ueL6fvuMfr1ZWXIPVu0'

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client['telegram_bot']
users_collection = db['users']
chats_collection = db['chats']
files_collection = db['files']

# Gemini API setup
GEMINI_API_KEY = 'AIzaSyDdaz9s4DfheY3T_jvWnKmzZdCKTyY3vHg'  # Replace with your actual Gemini API key
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    chat_id = update.message.chat_id

    # Check if user is already registered
    if not users_collection.find_one({'chat_id': chat_id}):
        users_collection.insert_one({
            'first_name': user.first_name,
            'username': user.username,
            'chat_id': chat_id,
            'phone_number': None
        })
        update.message.reply_text('Welcome! Please share your phone number.', reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton('Share phone number', request_contact=True)]], one_time_keyboard=True))
    else:
        update.message.reply_text('Welcome back!')

def contact(update: Update, context: CallbackContext) -> None:
    contact = update.message.contact
    chat_id = update.message.chat_id

    users_collection.update_one({'chat_id': chat_id}, {'$set': {'phone_number': contact.phone_number}})
    update.message.reply_text('Thank you! Your phone number has been saved.')

def handle_message(update: Update, context: CallbackContext) -> None:
    user_input = update.message.text
    chat_id = update.message.chat_id

    # Prepare the payload for the Gemini API
    payload = {
        "contents": [{
            "parts": [{"text": user_input}]
        }]
    }

    # Call Gemini API to get response
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
       
        response_json = response.json()

        #print("#########")
        #print(response_json);
        #print("##########");
        bot_response = response_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "Sorry, I couldn't process your request.")
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        bot_response = "Sorry, I couldn't process your request."

    # Save chat history
    chats_collection.insert_one({
        'chat_id': chat_id,
        'user_input': user_input,
        'bot_response': bot_response,
        'timestamp': update.message.date
    })

    update.message.reply_text(bot_response)




def handle_file(update: Update, context: CallbackContext) -> None:
    file = update.message.document or update.message.photo[-1]
    file_id = file.file_id
    file_name = file.file_name if hasattr(file, 'file_name') else 'photo.jpg'
    file_obj = context.bot.get_file(file_id)
    file_path = file_obj.file_path

    # Download the file content
    file_content = requests.get(file_path).content

    
    # Encode the file content to base64
    encoded_file = base64.b64encode(file_content).decode('utf-8')

    # Prepare the JSON payload
    payload = {
        "contents": [{
            "parts": [
                {"text": "Tell me about this instrument"},  # Adjust text as necessary
                {
                    "inline_data": {
                        "mime_type": 'image/jpeg',
                        "data": encoded_file
                    }
                }
            ]
        }]
    }

    # Call the Gemini API to analyze the image
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response_json = response.json()
        #print(response_json)

        # Extract the response content
        file_description = response_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "Sorry, I couldn't process your request.")
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        file_description = "Sorry, I couldn't analyze the file."

    # Save file metadata to MongoDB
    files_collection.insert_one({
        'chat_id': update.message.chat_id,
        'file_name': file_name,
        'description': file_description,
        'timestamp': update.message.date
    })

    # Send the bot response back to the user
    update.message.reply_text(file_description)


GOOGLE_API_KEY = "AIzaSyDUc1677hbZ0ogXEiFShBREnyH30LijUdM"
SEARCH_ENGINE_ID = "f2a64aa90c6c0472c"


def web_search(update: Update, context: CallbackContext) -> None:
    query = ' '.join(context.args)
    if not query:
        update.message.reply_text("Please provide a search query. Example: /websearch Python programming")
        return

    # Perform a Google search
    search_url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
    
    try:
        # Make the request to Google Custom Search API
        response = requests.get(search_url)
        results = response.json()

        if 'items' not in results:
            update.message.reply_text("No results found.")
            return

        # Extract titles, snippets, and URLs from search results
        search_results = []
        for item in results['items'][:5]:  # Limit to top 5 results
            title = item['title']
            link = item['link']
            snippet = item['snippet']
            search_results.append(f"{title}\n{snippet}\n{link}\n")
        
        # Join all results for summarization
        search_text = "\n\n".join(search_results)

        # Call Gemini API for summarization
        payload = {
            "contents": [{
                "parts": [{"text": f"Summarize the following search results:\n{search_text}"}]
            }]
        }

        headers = {'Content-Type': 'application/json'}
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response_json = response.json()

        # Extract summarized content from Gemini response
        summarized_text = response_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "Sorry, I couldn't summarize the results.")

        # Send summarized result to user
        update.message.reply_text(f"**Summary of Web Search Results**:\n\n{summarized_text}\n\nTop Links:\n" + "\n".join(search_results))
    
    except Exception as e:
        update.message.reply_text("Sorry, there was an error performing the web search.")
        print(f"Error: {e}")

def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(MessageHandler(Filters.contact, contact))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dispatcher.add_handler(MessageHandler(Filters.document | Filters.photo, handle_file))
    dispatcher.add_handler(CommandHandler('websearch', web_search))

    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
