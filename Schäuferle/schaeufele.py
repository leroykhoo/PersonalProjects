import requests
from bs4 import BeautifulSoup
import smtplib
from email.message import EmailMessage
import os
import datetime

# --- CONFIGURATION ---
URL = "https://www.werkswelt.de/?id=mohm"
KEYWORD = "schäufe"
SENDER_EMAIL = "leroykhoo11@gmail.com"
SENDER_PASSWORD = os.getenv("MENSA_PASSWORD")
# FIXED: Use a list of strings for multiple recipients
RECEIVER_EMAILS = ["leroykhoo11@gmail.com", "siahyeejoe@gmail.com"]

def send_alert(dish_name):
    msg = EmailMessage()
    msg.set_content(f"Gute Nachrichten! {dish_name.capitalize()} ist heute auf dem Speiseplan der Mensa Ohm!")
    msg['Subject'] = "Mensa Alert: SCHAEUFELE GEFUNDEN!"
    msg['From'] = SENDER_EMAIL
    # FIXED: Convert list to a comma-separated string for the header
    msg['To'] = ", ".join(RECEIVER_EMAILS)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(msg)
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def log_menu(content):
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    # Clean up the text to remove extra newlines for the log
    clean_content = " ".join(content.split())
    # FIXED: Added encoding="utf-8" to prevent crashes with German characters
    with open("menu_history.txt", "a", encoding="utf-8") as f:
        f.write(f"{date_str}: {clean_content[:150]}...\n")

def check_mensa():
    data = {'id': 'mohm', 'section': 'speiseplan'}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.post(URL, data=data, headers=headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        menu_text = soup.get_text().lower()
        
        # Log the menu first so you have a record even if Schäufele isn't found
        log_menu(menu_text)

        print("--- Checking for Schäufele ---")
        if KEYWORD in menu_text:
            print("Target found! Triggering email...")
            send_alert("Schäufele")
        else:
            print("No luck today. Better luck tomorrow!")

    except Exception as e:
        print(f"Script error: {e}")

if __name__ == "__main__":
    check_mensa()
