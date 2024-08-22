from flask import Flask, request, jsonify, render_template
import os
from dotenv import load_dotenv
from groq import Groq
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import threading
import time
import logging
from flask_cors import CORS

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Groq API setup
groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
SPREADSHEET_ID = os.getenv('1TzEMCPgvZnVs05ERyakO37BsAiOjomIvHeSdPZoczOc')

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=creds)

# Simulated knowledgebase
knowledgebase = {
    "FAQ's"
    "how to change trading account currency": "If you wish to change your trading account currency, you can easily do so by opening a new trading account on our client portal at https://portal.rcgmarkets.com/. After logging in, proceed to 'Account Settings' and navigate to 'Trading Accounts.' From there, you can open a new trading account and select the currency of your choice. Please be aware that you cannot modify the currency of an existing account, but opening a new account enables you to choose your preferred currency. If you have any inquiries or require assistance, please contact us!",
    
    "how to deposit": "To deposit funds into your account, simply log in to the Client Portal using this link https://portal.rcgmarkets.com/. Once you're logged in, navigate to the 'Fund Account' section. Here, you'll see all the available deposit methods. Select your preferred method and follow the instructions to complete your deposit.",
    
    "account verification - struggling to upload (alternative methods to submit documents)": "If you're struggling to upload your documents for account verification, you can alternatively submit them by sending an email to fica@rcgmarkets.com or by using our WhatsApp platform at +27824016338. We'll assist you further from there!",
    
    "withdrawal turnaround time": "Withdrawals take 24-48 working hours.",
    
    "why was my pdf bank statement declined": "Your bank statement was declined because it does not have a stamp. Other reasons may include different names from your client portal, lack of transactions, outdated information, or a blurry image. Please provide the required documents accordingly."
}

def create_app(config_name):
    app = Flask(__name__, template_folder=r'C:\Users\Mpho\RCG TEST GOOGLE\template')
    CORS(app)

    
    messages = []
    last_activity_time = time.time()
    conversation_ended = False

    def get_ai_response(messages):
        logger.info("Sending messages to Groq: %s", messages)
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=messages,
                temperature=1,
                max_tokens=1024,
                top_p=1,
                stream=False,
                stop=None,
            )
            ai_response = completion.choices[0].message.content
            logger.info("Received AI response: %s", ai_response)
            return ai_response
        except Exception as e:
            logger.error("Error in generating AI response: %s", str(e))
            return "Sorry, I couldn't process your request."

    def record_to_sheet(date, time, agent_name, transcript, assessment):
     try:
        sheet = sheets_service.spreadsheets()
        values = [[date, time, agent_name, transcript, assessment]]
        body = {'values': values}
        result = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID, range='Sheet1',
            valueInputOption='USER_ENTERED', body=body).execute()
        logger.info("Recorded to sheet: %s", result)
        return "Recorded to sheet successfully"
     except Exception as e:
        logger.error("Error recording to sheet: %s", str(e))
        return "Error recording to sheet"

    def check_timeout():
        nonlocal conversation_ended
        while not conversation_ended:
            if time.time() - last_activity_time > 60:  # 1 minutes
                end_conversation("Timeout")
                break
            time.sleep(10)  # Check every 10 seconds

    def end_conversation(reason):
        nonlocal conversation_ended
        if not conversation_ended:
            conversation_ended = True
            transcript = "\n".join([f"{m['role']}: {m['content']}" for m in messages[1:]])
            now = datetime.datetime.now()
            date = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            record_to_sheet(date, time_str, "AI Agent", transcript, f"Conversation ended due to {reason}")

    @app.route('/')
    def home():
        return render_template('index.html')

    @app.route('/chat', methods=['POST'])
    def chat():
        nonlocal last_activity_time, messages
        last_activity_time = time.time()
        
        if not messages:
            system_message = """Here's a more concise version:

# Forex Customer Service Interview Chatbot

You are a frustrated RCG Markets forex customer testing their support.

## Core Behaviors:
1. Start angry, use offensive language
2. Become calmer over time
3. Use conversational language
4. Ask only FAQ questions in order
5. Keep responses short
6. Move on if answers match FAQ
7. Ask follow-ups if needed
8. Cover all FAQ questions
9. Note incorrect information
10. End politely

## Process:
1. Begin frustrated
2. Ask first FAQ question
3. Check answer against FAQ
4. Progress through all questions
5. Adjust tone as you go
6. End conversation politely

## Language:
- Initially offensive
- Natural, conversational
- Concise questions/responses

## Evaluation:
- Answer accuracy
- FAQ completeness
- Frustration management

Start when ready, responding as the customer."""
            messages.append({"role": "system", "content": system_message})

        user_message = request.json['message']
        logger.info("User message received: %s", user_message)
        messages.append({"role": "user", "content": user_message})
        
        # Check if the user's message matches any FAQ in the knowledgebase
        user_message_lower = user_message.lower()
        ai_response = knowledgebase.get(user_message_lower, get_ai_response(messages))
        messages.append({"role": "assistant", "content": ai_response})
        
        return jsonify({"response": ai_response})

    # Start the timeout checking thread
    timeout_thread = threading.Thread(target=check_timeout)
    timeout_thread.start()

    return app

if __name__ == "__main__":
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    app.run(debug=True)
