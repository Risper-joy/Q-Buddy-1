from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/call_ticket', methods=['POST'])
def call_ticket():
    # Send a message to the Rasa bot
    rasa_url = "http://localhost:5005/webhooks/rest/webhook"
    payload = {
        "sender": "user",  # Can be any user id
        "message": "call ticket"  # This will trigger the intent
    }
    
    try:
        response = requests.post(rasa_url, json=payload)
        response_data = response.json()

        # Extract the message from the bot's response
        if response_data:
            bot_message = response_data[0]['text']
            return jsonify({"message": bot_message})
        else:
            return jsonify({"message": "No response from bot."})
    
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)
