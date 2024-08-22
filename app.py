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
    
    "available account types": "Classic – mt4 account, ECN – mt4 account, Raw – mt4 account, Royal 100 – mt5 account (bonus), Royal cent – mt5 cent account.",
    
    "how to change trading account password": "To change your trading account password, please follow these steps: Log in to your client portal using this link: https://portal.rcgmarkets.com/. Navigate to the 'Account Settings' tab. Click on 'Change Password.' You will be presented with two options: 'Change Client Portal Password' and 'Change Trading Account Password.' Select 'Change Trading Account Password' and choose the trading account for which you want to change the password. Click 'Submit'.",
    
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
            system_message = """You are a frustrated customer interacting with RCG Markets' forex brokerage customer service. Your task is to test their knowledge and service quality using provided FAQs.

            Instructions:
            start with the last question in the FAQ provided
            1. Begin with a very frustrated tone then become more understanding as the converstion progresses
            2. Use natural, conversational language
            3. Only ask the qustions in the FAQ proivded 
            4. Always be short with your questions and replies
            6. Ask follow-up questions if needed
            7. Only ask one of the question from the FAQ
            7. Note any incorrect/incomplete information
            8. End conversations politely

            Begin the conversation when ready. Respond as the customer, awaiting the support agent's (user's) replies."""
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