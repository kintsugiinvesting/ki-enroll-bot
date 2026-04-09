import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
THRIVECART_API_KEY = os.getenv("THRIVECART_API_KEY")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))

COURSES = {
    "essentials": {"name": "Intellivestor Essentials", "id": 1},
    "accelerate": {"name": "Intellivestor Accelerate", "id": 2},
    "rt1m": {"name": "Intellivestor Road to 1 Million", "id": 5},
}

sessions = {}


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)


def send_course_buttons(chat_id):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📘 Essentials", "callback_data": "course_essentials"},
                {"text": "🚀 Accelerate", "callback_data": "course_accelerate"},
            ],
            [
                {"text": "🏆 Road to 1 Million (RT1M)", "callback_data": "course_rt1m"},
            ],
        ]
    }
    send_message(chat_id, "Which course?", reply_markup=keyboard)


def send_confirm_buttons(chat_id, session):
    text = (
        f"Please confirm enrollment:\n\n"
        f"👤 *Name:* {session['name']}\n"
        f"📧 *Email:* {session['email']}\n"
        f"📚 *Course:* {session['course_name']}\n"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm", "callback_data": "confirm_yes"},
                {"text": "❌ Cancel", "callback_data": "confirm_no"},
            ]
        ]
    }
    send_message(chat_id, text, reply_markup=keyboard)


def enroll_student(name, email, product_id):
    url = "https://thrivecart.com/api/external/students"
    headers = {
        "Authorization": f"Bearer {THRIVECART_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "course_id": product_id,
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.status_code, response.json()


def answer_callback(callback_query_id):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id}
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "callback_query" in data:
        cq = data["callback_query"]
        user_id = cq["from"]["id"]
        chat_id = cq["message"]["chat"]["id"]
        cb_data = cq["data"]
        answer_callback(cq["id"])

        if user_id != ALLOWED_USER_ID:
            send_message(chat_id, "⛔ Unauthorized.")
            return jsonify(ok=True)

        session = sessions.get(user_id, {})

        if cb_data.startswith("course_"):
            course_key = cb_data.replace("course_", "")
            course = COURSES.get(course_key)
            if course and session.get("step") == "awaiting_course":
                session["course_key"] = course_key
                session["course_name"] = course["name"]
                session["course_id"] = course["id"]
                session["step"] = "awaiting_confirm"
                sessions[user_id] = session
                send_confirm_buttons(chat_id, session)

        elif cb_data == "confirm_yes":
            if session.get("step") == "awaiting_confirm":
                send_message(chat_id, "⏳ Enrolling student...")
                status, result = enroll_student(
                    session["name"], session["email"], session["course_id"]
                )
                if status in (200, 201):
                    send_message(
                        chat_id,
                        f"✅ *Done!* {session['name']} has been enrolled in *{session['course_name']}*.\n\nA receipt has been sent to {session['email']}."
                    )
                else:
                    error_msg = result.get("message", str(result))
                    send_message(
                        chat_id,
                        f"❌ Enrollment failed.\n\n*Error:* {error_msg}\n\nPlease check ThriveCart or try again."
                    )
                sessions.pop(user_id, None)

        elif cb_data == "confirm_no":
            sessions.pop(user_id, None)
            send_message(chat_id, "❌ Cancelled. Send /enroll to start again.")

        return jsonify(ok=True)

    if "message" not in data:
        return jsonify(ok=True)

    msg = data["message"]
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if user_id != ALLOWED_USER_ID:
        send_message(chat_id, "⛔ Unauthorized.")
        return jsonify(ok=True)

    session = sessions.get(user_id, {})

    if text in ("/start", "/help"):
        send_message(chat_id, "👋 Welcome to the *KI Enrollment Bot*!\n\nSend /enroll to enroll a new student.")

    elif text == "/enroll":
        sessions[user_id] = {"step": "awaiting_name"}
        send_message(chat_id, "What is the student's *full name*?")

    elif session.get("step") == "awaiting_name":
        session["name"] = text
        session["step"] = "awaiting_email"
        sessions[user_id] = session
        send_message(chat_id, f"Got it. What is *{text}'s* email address?")

    elif session.get("step") == "awaiting_email":
        if "@" not in text or "." not in text:
            send_message(chat_id, "⚠️ That doesn't look like a valid email. Please try again.")
        else:
            session["email"] = text.lower()
            session["step"] = "awaiting_course"
            sessions[user_id] = session
            send_course_buttons(chat_id)

    else:
        send_message(chat_id, "Send /enroll to enroll a new student.")

    return jsonify(ok=True)


@app.route("/", methods=["GET"])
def health():
    return "KI Enroll Bot is running ✅", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
