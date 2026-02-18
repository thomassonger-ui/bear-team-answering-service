from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
import anthropic
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import json
import pytz

load_dotenv()

# ─────────────────────────────────────────────
#  BEAR TEAM CONFIGURATION — Edit this section
# ─────────────────────────────────────────────
BROKERAGE_NAME = "Bear Team Real Estate"
BROKERAGE_CITY = "Orlando, Florida"
BROKERAGE_ADDRESS = "2300 S Crystal Lake Dr, Orlando, FL 32806"
BROKERAGE_PHONE = "407-375-3321"
BROKERAGE_EMAIL = "info@bearteam.com"
TIMEZONE = "America/New_York"
BUSINESS_HOURS_START = 8    # 8 AM
BUSINESS_HOURS_END = 17     # 5 PM
BUSINESS_DAYS = [0,1,2,3,4] # Mon-Fri (Sat/Sun by appointment)

# Agent routing — name, role, phone, email
AGENTS = {
    "sellers": {
        "name": "Bethanne Baer",
        "role": "Broker / Listing Specialist",
        "phone": "407-228-1112",
        "email": "Bethanne@bearteam.com"
    },
    "rentals": {
        "name": "Owen Willis",
        "role": "Property Manager",
        "phone": "407-228-1112",
        "email": "owen@bearteam.com"
    },
    "buyers1": {
        "name": "Lissette Dennis",
        "role": "Buyer's Agent",
        "phone": "407-577-9924",
        "email": "lissette@bearteam.com"
    },
    "buyers2": {
        "name": "Shanelle Mitchell",
        "role": "Buyer's Agent",
        "phone": "407-491-8811",
        "email": "shanelle@bearteam.com"
    }
}
# ─────────────────────────────────────────────

# Environment variables
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
YOUR_PHONE_NUMBER = os.environ.get('YOUR_PHONE_NUMBER')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL')
BASE_URL = os.environ.get('BASE_URL', '').rstrip('/')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')
GOOGLE_CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID')

EASTERN = pytz.timezone(TIMEZONE)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bear-team-secret')

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
conversations = {}

BUSINESS_KNOWLEDGE = """
BEAR TEAM REAL ESTATE — ORLANDO, FLORIDA

WHO WE ARE:
Bear Team Real Estate LLC is a full-service real estate brokerage in Orlando, Florida.
We help buyers find their perfect home, sellers get top dollar, and renters find great properties.

OFFICE INFORMATION:
- Address: 2300 S Crystal Lake Dr, Orlando, FL 32806
- Phone: 407-375-3321
- Email: info@bearteam.com
- Website: bearteam.com

OFFICE HOURS:
- Monday to Friday: 8 AM to 5 PM Eastern Time
- Saturday and Sunday: By appointment only
- AI answering service available 24/7

OUR TEAM:
1. Bethanne Baer — Broker / Listing Specialist (Sellers)
   - Specializes in listing and selling homes in the Orlando area
   - Expert in pricing strategy, marketing, and negotiations
   - Phone: 407-228-1112 | Email: Bethanne@bearteam.com

2. Owen Willis — Property Manager (Rentals)
   - Handles all rental properties and tenant inquiries
   - Manages lease agreements, maintenance, and property showings
   - Phone: 407-228-1112 | Email: owen@bearteam.com

3. Lissette Dennis — Buyer's Agent
   - Helps buyers find and purchase homes in Orlando
   - Expert in first-time buyers, relocations, and investment properties
   - Phone: 407-577-9924 | Email: lissette@bearteam.com

4. Shanelle Mitchell — Buyer's Agent
   - Helps buyers find and purchase homes in Orlando
   - Expert in family homes, new construction, and move-up buyers
   - Phone: 407-491-8811 | Email: shanelle@bearteam.com

SERVICES:
- Buyer Representation: Help buyers find and purchase homes in Orlando and surrounding areas
- Seller Representation: List, market, and sell homes for maximum value
- Rental & Property Management: Find rental properties, manage leases and tenants
- Investment Properties: Identify and acquire investment properties
- Relocation Services: Help people moving to the Orlando area find the right home

AREAS SERVED:
Orlando and surrounding areas including: Winter Park, Kissimmee, Sanford, Lake Nona,
Dr. Phillips, Windermere, Ocoee, Apopka, Altamonte Springs, and all of Central Florida

BUYING A HOME:
- Free buyer consultation available
- We help with pre-approval guidance, home search, offers, inspections, and closing
- No cost to buyers — our commission is paid by the seller
- We work with all price ranges and first-time buyers welcome

SELLING A HOME:
- Free home valuation / comparative market analysis available
- Professional photography, MLS listing, and marketing included
- Negotiation experts to get you the best price
- Contact Bethanne Baer for listing consultations

RENTALS:
- We manage and list rental properties throughout Orlando
- Contact Owen Willis for rental inquiries, availability, and showings
- Both long-term and short-term rentals available

SCHEDULING:
- Home showings available Monday-Sunday with advance notice
- Free consultations available Monday-Friday 8 AM to 5 PM
- Weekend appointments available by request

IF SOMEONE ASKS ABOUT BUYING A HOME:
Route them to Lissette Dennis (407-577-9924) or Shanelle Mitchell (407-491-8811).
Offer to schedule a free buyer consultation.

IF SOMEONE ASKS ABOUT SELLING A HOME:
Route them to Bethanne Baer (407-228-1112 / Bethanne@bearteam.com).
Offer a free home valuation.

IF SOMEONE ASKS ABOUT RENTALS:
Route them to Owen Willis (407-228-1112 / owen@bearteam.com).

IF SOMEONE ASKS ABOUT PRICING OR HOME VALUES:
Explain that pricing depends on the specific property and market conditions.
Offer a free comparative market analysis with Bethanne.
"""

class ConversationManager:
    def __init__(self, caller_id):
        self.caller_id = caller_id
        self.attempt_count = 0
        self.conversation_history = []
        self.caller_questions = []
        self.caller_intent = None  # 'buyer', 'seller', 'renter', 'general'

    def add_question(self, question):
        self.attempt_count += 1
        self.caller_questions.append(question)
        self.conversation_history.append({"role": "user", "content": question})
        # Detect intent
        q = question.lower()
        if any(w in q for w in ['buy', 'buying', 'purchase', 'looking for a home', 'find a house']):
            self.caller_intent = 'buyer'
        elif any(w in q for w in ['sell', 'selling', 'list', 'listing', 'value my home', 'what is my home worth']):
            self.caller_intent = 'seller'
        elif any(w in q for w in ['rent', 'rental', 'lease', 'tenant', 'apartment', 'property management']):
            self.caller_intent = 'renter'

    def add_response(self, response):
        self.conversation_history.append({"role": "assistant", "content": response})

    def should_escalate(self):
        return self.attempt_count >= 8

    def get_agent_for_intent(self):
        if self.caller_intent == 'seller':
            return AGENTS['sellers']
        elif self.caller_intent == 'renter':
            return AGENTS['rentals']
        elif self.caller_intent == 'buyer':
            # Alternate between buyer agents
            return AGENTS['buyers1'] if self.attempt_count % 2 == 0 else AGENTS['buyers2']
        return None

    def get_summary(self):
        summary = "Caller: " + self.caller_id + "\n"
        summary += "Time: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n"
        summary += "Intent: " + (self.caller_intent or "Unknown") + "\n\n"
        for i, question in enumerate(self.caller_questions, 1):
            summary += "Q" + str(i) + ": " + question + "\n"
        return summary

    def get_full_conversation(self):
        return "\n".join(self.caller_questions)

class AIAgent:
    def answer_question(self, question, conversation_history=None):
        if not anthropic_client:
            return "I apologize, our system is having trouble right now."

        system_prompt = f"""You are a friendly and professional receptionist for Bear Team Real Estate in Orlando, Florida.

CRITICAL FORMATTING RULE: Your response will be read aloud word-for-word by a text-to-speech phone system. You must NEVER use asterisks, markdown, bold, italics, bullet points, numbered lists, hashtags, underscores, or any special formatting characters. Write plain conversational sentences only. If you put an asterisk around a word like *buying*, the phone system will literally say "asterisk buying asterisk" to the caller.

IMPORTANT — USE THIS INFORMATION TO ANSWER ALL QUESTIONS:
{BUSINESS_KNOWLEDGE}

Communication Guidelines:
- Keep answers warm, natural, and brief — this is a phone call
- Speak like a real, knowledgeable person — not a robot
- Write in plain spoken English only — no formatting of any kind
- Always use the business information above for accurate answers
- If asked about something you don't know, say: "That's a great question — let me have one of our agents call you right back with those details."
- IMPORTANT: End responses naturally. Only ask a follow-up question when it makes sense — never robotically repeat "Is there anything else I can help you with?"

IMPORTANT GOAL: Your main job is to gather the callers information and set up an appointment. For every caller, you should collect their name, confirm their phone number, and ask what day and time works best for them. Do this naturally within the conversation.

When a caller wants to BUY a home:
- Be enthusiastic and helpful
- Mention that buyer representation is FREE to them
- Ask their name and what type of home they are looking for
- Ask what day and time works best for a free consultation
- Offer to connect them with Lissette or Shanelle

When a caller wants to SELL a home:
- Be enthusiastic and ask about their property
- Ask their name
- Mention our free home valuation
- Ask what day and time works best to meet with Bethanne Baer

When a caller asks about RENTALS:
- Ask their name and what they are looking for
- Ask what day and time works best
- Offer to connect them with Owen Willis

For ALL callers:
1. Get their name
2. Confirm their phone number by reading it back to them
3. Ask what day and time works best for an appointment or consultation
4. Let them know the appropriate agent will call to confirm

Always be warm, professional, and helpful. Bear Team Real Estate serves all of Orlando and Central Florida."""

        messages = conversation_history or []
        if not messages or messages[-1]["content"] != question:
            messages.append({"role": "user", "content": question})

        try:
            response = anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                system=system_prompt,
                messages=messages
            )
            return response.content[0].text
        except Exception as e:
            return "Sorry, I'm having a little trouble right now. Please hold and someone will be right with you."

ai_agent = AIAgent()

# ── Google Helpers ──

def get_google_credentials(scopes):
    if GOOGLE_CREDENTIALS_JSON:
        info = json.loads(GOOGLE_CREDENTIALS_JSON)
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        return Credentials.from_service_account_info(info, scopes=scopes)
    else:
        return Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)

def get_sheets_client():
    try:
        creds = get_google_credentials(['https://www.googleapis.com/auth/spreadsheets'])
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Sheets error: {e}")
        return None

def get_calendar_service():
    try:
        creds = get_google_credentials(['https://www.googleapis.com/auth/calendar'])
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"Calendar error: {e}")
        return None

def log_to_sheets(caller_id, call_type, intent, conversation_text, agent_name='', voicemail_text=''):
    if not GOOGLE_SHEET_ID:
        return
    try:
        client = get_sheets_client()
        if not client:
            return
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
        if sheet.row_count == 0 or sheet.cell(1, 1).value != 'Date':
            sheet.insert_row(['Date', 'Time', 'Caller Phone', 'Call Type', 'Intent', 'Assigned Agent', 'Conversation', 'Voicemail'], 1)
        now = datetime.now()
        sheet.append_row([
            now.strftime('%Y-%m-%d'),
            now.strftime('%I:%M %p ET'),
            caller_id,
            call_type,
            intent or 'General',
            agent_name,
            conversation_text,
            voicemail_text
        ])
        print(f"Logged: {call_type} from {caller_id}")
    except Exception as e:
        print(f"Sheets log error: {e}")

def get_available_slots(days_ahead=5):
    if not GOOGLE_CALENDAR_ID:
        return []
    try:
        service = get_calendar_service()
        if not service:
            return []
        now = datetime.now(EASTERN)
        end_date = now + timedelta(days=days_ahead)
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=now.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        busy = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime')
            end = event['end'].get('dateTime')
            if start and end:
                busy.append((
                    datetime.fromisoformat(start).astimezone(EASTERN),
                    datetime.fromisoformat(end).astimezone(EASTERN)
                ))
        slots = []
        check = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while check < end_date and len(slots) < 4:
            if check.weekday() in BUSINESS_DAYS and BUSINESS_HOURS_START <= check.hour < BUSINESS_HOURS_END:
                slot_end = check + timedelta(hours=1)
                if not any(b[0] < slot_end and b[1] > check for b in busy):
                    slots.append(check)
            check += timedelta(hours=1)
        return slots
    except Exception as e:
        print(f"Calendar slots error: {e}")
        return []

def book_appointment(caller_phone, slot_datetime, agent, intent):
    if not GOOGLE_CALENDAR_ID:
        return False
    try:
        service = get_calendar_service()
        if not service:
            return False
        end_time = slot_datetime + timedelta(hours=1)
        intent_label = {'buyer': 'Buyer Consultation', 'seller': 'Listing Consultation', 'renter': 'Rental Inquiry'}.get(intent, 'Consultation')
        event = {
            'summary': f'Bear Team — {intent_label} with {caller_phone}',
            'description': f'Caller: {caller_phone}\nType: {intent_label}\nAgent: {agent["name"] if agent else "TBD"}\nBooked via AI phone system.',
            'start': {'dateTime': slot_datetime.isoformat(), 'timeZone': TIMEZONE},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': TIMEZONE},
            'reminders': {'useDefault': False, 'overrides': [
                {'method': 'email', 'minutes': 60},
                {'method': 'popup', 'minutes': 30}
            ]}
        }
        service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        print(f"Booked: {intent_label} for {caller_phone} at {slot_datetime}")
        return True
    except Exception as e:
        print(f"Calendar booking error: {e}")
        return False

# ── Email Helper ──

def send_email(subject, body):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD or not NOTIFICATION_EMAIL:
        print("Email not configured")
        return
    server = None
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Email error: {e}")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

def send_lead_email(conversation, agent, booked_slot=None):
    intent = conversation.caller_intent or 'general'
    intent_label = {'buyer': 'BUYER LEAD', 'seller': 'SELLER LEAD', 'renter': 'RENTAL INQUIRY'}.get(intent, 'NEW INQUIRY')
    body = f"{intent_label} — Bear Team Real Estate\n"
    body += "=" * 50 + "\n\n"
    body += f"Caller Phone: {conversation.caller_id}\n"
    body += f"Call Time: {datetime.now().strftime('%Y-%m-%d %I:%M %p ET')}\n"
    body += f"Intent: {intent.upper()}\n"
    if agent:
        body += f"Assigned Agent: {agent['name']} ({agent['role']})\n"
        body += f"Agent Phone: {agent['phone']}\n"
    if booked_slot:
        body += f"\nAPPOINTMENT BOOKED: {booked_slot.strftime('%A, %B %d at %I:%M %p ET')}\n"
    body += f"\nCONVERSATION:\n{'-'*50}\n{conversation.get_full_conversation()}\n{'-'*50}\n"
    body += f"\nACTION: Call {conversation.caller_id} to follow up.\n"
    log_to_sheets(conversation.caller_id, intent_label, intent, conversation.get_full_conversation(),
                  agent['name'] if agent else '')
    send_email(f"Bear Team — {intent_label} from {conversation.caller_id}", body)

def send_voicemail_email(conversation, voicemail_text):
    body = f"New Voicemail — Bear Team Real Estate\n\n{conversation.get_summary()}\nMessage: {voicemail_text}"
    log_to_sheets(conversation.caller_id, 'Voicemail', conversation.caller_intent,
                  conversation.get_full_conversation(), '', voicemail_text)
    send_email(f"Bear Team — Voicemail from {conversation.caller_id}", body)

# ── Flask Routes ──

@app.route("/voice", methods=['GET', 'POST'])
def handle_incoming_call():
    response = VoiceResponse()
    caller_id = request.values.get('From', 'Unknown')
    call_sid = request.values.get('CallSid', 'Unknown')
    if call_sid not in conversations:
        conversations[call_sid] = ConversationManager(caller_id)
    response.say("Thank you for calling Bear Team Real Estate in Orlando! How can I help you today?",
                 voice='Google.en-US-Neural2-F', language='en-US')
    gather = Gather(input='speech', action=BASE_URL + '/process_speech', speech_timeout='auto', language='en-US')
    response.append(gather)
    response.redirect(BASE_URL + '/voice')
    return str(response)

@app.route("/process_speech", methods=['POST'])
def process_speech():
    response = VoiceResponse()
    speech_result = request.values.get('SpeechResult', '').strip()
    call_sid = request.values.get('CallSid', 'Unknown')
    caller_id = request.values.get('From', 'Unknown')
    if call_sid not in conversations:
        conversations[call_sid] = ConversationManager(caller_id)
    conversation = conversations[call_sid]
    if not speech_result:
        response.say("Sorry, I didn't catch that. Could you repeat that?", voice='Google.en-US-Neural2-F')
        response.redirect(BASE_URL + '/voice')
        return str(response)
    conversation.add_question(speech_result)

    # Let the AI handle the conversation naturally — it will ask for name, number, and appointment time
    ai_answer = ai_agent.answer_question(speech_result, conversation.conversation_history)
    # Strip ALL markdown/formatting characters that TTS would read aloud
    import re
    ai_answer = re.sub(r'[*#_~`\[\]()>]', '', ai_answer)
    ai_answer = re.sub(r'\s+', ' ', ai_answer).strip()
    conversation.add_response(ai_answer)

    # Check if caller wants to end the call
    goodbye_words = ['bye', 'goodbye', 'thank you', 'thanks', 'that is all', "that's all", 'no thanks', 'nothing else', 'have a good day']
    is_goodbye = any(w in speech_result.lower() for w in goodbye_words)

    if is_goodbye or conversation.should_escalate():
        # Conversation is wrapping up — send lead email and book if possible
        agent = conversation.get_agent_for_intent()
        has_appointment_mention = any(w in q.lower() for q in conversation.caller_questions for w in
            ['appointment', 'schedule', 'showing', 'consultation', 'book', 'meeting', 'visit', 'come in'])
        if has_appointment_mention:
            slots = get_available_slots(days_ahead=5)
            if slots:
                booked_slot = slots[0]
                book_appointment(caller_id, booked_slot, agent, conversation.caller_intent)
                send_lead_email(conversation, agent, booked_slot)
            else:
                send_lead_email(conversation, agent)
        else:
            send_lead_email(conversation, agent)
        response.say(ai_answer, voice='Google.en-US-Neural2-F', language='en-US')
        response.say("Thanks for calling Bear Team Real Estate! Have a great day!", voice='Google.en-US-Neural2-F')
        response.hangup()
        return str(response)

    # Continue the conversation — let AI keep talking to the caller
    response.say(ai_answer, voice='Google.en-US-Neural2-F', language='en-US')
    gather = Gather(input='speech', action=BASE_URL + '/process_speech', speech_timeout='auto', timeout=8)
    response.append(gather)
    response.say("Are you still there? If not, thanks for calling Bear Team Real Estate!", voice='Google.en-US-Neural2-F')
    response.hangup()
    return str(response)

@app.route("/handle_voicemail", methods=['POST'])
def handle_voicemail():
    response = VoiceResponse()
    response.say("Thank you! We'll call you back as soon as possible. Have a great day!", voice='Google.en-US-Neural2-F')
    response.hangup()
    return str(response)

@app.route("/handle_transcription", methods=['POST'])
def handle_transcription():
    call_sid = request.values.get('CallSid', 'Unknown')
    transcription = request.values.get('TranscriptionText', '')
    if call_sid in conversations:
        send_voicemail_email(conversations[call_sid], transcription)
    return '', 200

@app.route("/status")
def status():
    return {"status": "running", "brokerage": BROKERAGE_NAME, "base_url": BASE_URL or "NOT SET"}

@app.route("/")
def home():
    return {"message": f"{BROKERAGE_NAME} — {BROKERAGE_CITY} — AI Phone System"}
