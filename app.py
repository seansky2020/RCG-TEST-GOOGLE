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
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=creds)



def create_app(config_name):
    app = Flask(__name__)
    
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
        except Exception as e:
            logger.error("Error recording to sheet: %s", str(e))

    def check_timeout():
        nonlocal conversation_ended
        while not conversation_ended:
            if time.time() - last_activity_time > 600:  # 10 minutes
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
            system_message = """You are a potential customer interacting with RCG Markets' forex brokerage customer service. Your task is to test their knowledge and service quality using provided FAQs.

            Instructions:
            1. Use natural, conversational language
            2. Alternate between novice and experienced trader personas
            3. Ask follow-up questions based on responses
            4. Note any incorrect/incomplete information
            5. End conversations politely

            Begin the conversation when ready. Respond as the customer, awaiting the support agent's (user's) replies."""
            messages.append({"role": "system", "content": system_message})

        user_message = request.json['message']
        logger.info("User message received: %s", user_message)
        messages.append({"role": "user", "content": user_message})
        
        ai_response = get_ai_response(messages)
        messages.append({"role": "assistant", "content": ai_response})
        
        return jsonify({"response": ai_response})

    # Start the timeout checking thread
    timeout_thread = threading.Thread(target=check_timeout)
    timeout_thread.start()

    return app

if __name__ == "__main__":
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    app.run(debug=True)